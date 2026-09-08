"""Additive Task delivery. No entry point generates a human review decision."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from src.contracts import reviewed_output_contract_errors
from src.fhir_client import (
    FHIRClient,
    FHIRClientError,
    FHIRResponseError,
    FHIRRetryLaterError,
    _normalize_base_url,
    _validate_fhir_id,
)
from src.utils import load_json_file, save_json_file

IDENTIFIER_SYSTEM = (
    "https://github.com/NickLeko/FHIR-Referral-Intake-Review/review-event"
)
DEFAULT_OUTBOX = Path("outputs/integration/outbox.sqlite3")
DEFAULT_REVIEW_DIR = Path("outputs/review_history/live")


class ReviewGateError(ValueError):
    pass


def _canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


def review_task(reviewed, base_url):
    """Require the existing reviewed contract and exactly one live source referral."""
    try:
        if not isinstance(reviewed, dict) or reviewed_output_contract_errors(reviewed):
            raise ReviewGateError(
                "A valid human-reviewed output is required for write-back."
            )
    except (TypeError, AttributeError):
        raise ReviewGateError(
            "A valid human-reviewed output is required for write-back."
        ) from None
    if not reviewed["reviewer_name"].strip():
        raise ReviewGateError("A reviewer name is required for write-back.")
    try:
        instant = datetime.fromisoformat(reviewed["reviewed_at"].replace("Z", "+00:00"))
        if instant.tzinfo is None:
            raise ValueError()
    except ValueError:
        raise ReviewGateError("Review timestamp must include a timezone.") from None
    base_url = _normalize_base_url(base_url)
    provenance = reviewed["extracted_review_packet"].get("input_provenance", {})
    resources = provenance.get("resources", [])
    if provenance.get("source_type") != "live" or not resources:
        raise ReviewGateError(
            "Only a reviewed live packet may be written to its original server."
        )
    if any(_normalize_base_url(r["server_base_url"]) != base_url for r in resources):
        raise ReviewGateError(
            "Write destination does not match the reviewed source server."
        )
    roots = [r for r in resources if r["resource_type"] == "ServiceRequest"]
    if len(roots) != 1:
        raise ReviewGateError(
            "Write-back requires exactly one original ServiceRequest."
        )
    source_id = _validate_fhir_id(roots[0]["resource_id"], name="ServiceRequest id")
    digest = hashlib.sha256(
        _canonical({"server": base_url, "reviewed": reviewed}).encode()
    ).hexdigest()
    task = {
        "resourceType": "Task",
        "identifier": [{"system": IDENTIFIER_SYSTEM, "value": digest}],
        "status": "completed",
        "intent": "order",
        "code": {"text": "Referral intake human review"},
        "businessStatus": {"text": reviewed["final_status"]},
        "focus": {"reference": f"ServiceRequest/{source_id}"},
        "authoredOn": reviewed["reviewed_at"],
        "lastModified": reviewed["reviewed_at"],
        "owner": {"display": reviewed["reviewer_name"]},
        "note": [
            {
                "authorString": reviewed["reviewer_name"],
                "time": reviewed["reviewed_at"],
                "text": reviewed["reviewer_note"]
                or "No additional reviewer note provided.",
            }
        ],
        "output": [
            {
                "type": {"text": "Human review decision"},
                "valueString": reviewed["human_review_decision"],
            },
            {
                "type": {"text": "Initial packet status"},
                "valueString": reviewed["status_before_review"],
            },
            {
                "type": {"text": "Next administrative step"},
                "valueString": reviewed["recommended_next_admin_step"],
            },
        ],
    }
    return digest, task


def _existing_task(client, task, key):
    bundle = client.find_tasks(f"{IDENTIFIER_SYSTEM}|{key}")
    entries = bundle.get("entry", [])
    total = bundle.get("total", len(entries))
    if (
        isinstance(total, bool)
        or not isinstance(total, int)
        or total != len(entries)
        or len(entries) > 1
        or any(link["relation"] == "next" for link in bundle.get("link", []))
    ):
        raise FHIRResponseError(
            client.base_url, "Task identifier is ambiguous or search is incomplete"
        )
    if not entries:
        return None
    existing = entries[0]["resource"]
    if (
        any(existing.get(k) != v for k, v in task.items())
        or entries[0].get("search", {}).get("mode", "match") != "match"
    ):
        raise FHIRResponseError(
            client.base_url, "existing Task conflicts with the reviewed disposition"
        )
    resource_id = _validate_fhir_id(existing.get("id"), name="Task id")
    return f"Task/{resource_id}"


class ReviewOutbox:
    """SQLite receipts plus unchanged reviewed JSON; no tokens or keys are persisted.

    A committed pending row precedes every attempt. Replaying any non-delivered
    row uses the same review hash and conditional create. Delivered is monotonic.
    """

    def __init__(self, path: Path = DEFAULT_OUTBOX):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS deliveries (
                review_id TEXT PRIMARY KEY, base_url TEXT NOT NULL,
                artifact_path TEXT NOT NULL, state TEXT NOT NULL,
                detail TEXT NOT NULL, task_reference TEXT)""")
            db.execute(
                "CREATE TABLE IF NOT EXISTS cooldowns (base_url TEXT PRIMARY KEY, retry_at REAL NOT NULL)"
            )
        self.path.chmod(0o600)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def enqueue(self, reviewed, *, base_url, output_dir=DEFAULT_REVIEW_DIR):
        key, _ = review_task(reviewed, base_url)
        artifact = (Path(output_dir) / f"{key}.json").resolve()
        if artifact.exists():
            if load_json_file(artifact) != reviewed:
                raise ReviewGateError(
                    "Existing local reviewed artifact conflicts; human investigation required."
                )
        else:
            save_json_file(artifact, reviewed)
        with self._connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO deliveries VALUES (?, ?, ?, 'pending', 'Awaiting delivery', NULL)",
                (key, _normalize_base_url(base_url), str(artifact)),
            )
        return self.get(key)

    def get(self, key):
        with self._connect() as db:
            row = db.execute(
                "SELECT d.*, c.retry_at FROM deliveries d LEFT JOIN cooldowns c USING (base_url) WHERE review_id = ?",
                (key,),
            ).fetchone()
        if row is None:
            raise ReviewGateError("Unknown review delivery.")
        return dict(row)

    def list(self):
        with self._connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT d.*, c.retry_at FROM deliveries d LEFT JOIN cooldowns c USING (base_url) ORDER BY d.rowid"
                )
            ]

    def _record(self, key, state, detail, task_reference=None):
        with self._connect() as db:
            db.execute(
                "UPDATE deliveries SET state=?, detail=?, task_reference=? WHERE review_id=? AND state != 'delivered'",
                (state, detail, task_reference, key),
            )
        return self.get(key)

    def deliver(self, key, client: FHIRClient):
        row = self.get(key)
        if row["base_url"] != client.base_url:
            raise ReviewGateError(
                "Delivery client does not match the original source server."
            )
        if row["state"] == "delivered":
            return row
        with self._connect() as db:
            cooldown = db.execute(
                "SELECT retry_at FROM cooldowns WHERE base_url=?", (client.base_url,)
            ).fetchone()
        if cooldown and cooldown["retry_at"] > time.time():
            return self._record(
                key,
                row["state"],
                "Server Retry-After is still active; replay this saved review after the cooldown.",
            )
        attempted_write = row["state"] == "uncertain"
        try:
            reviewed = load_json_file(Path(row["artifact_path"]))
            actual_key, task = review_task(reviewed, row["base_url"])
            if actual_key != key:
                raise ReviewGateError(
                    "Reviewed artifact changed; do not retry a different disposition under this key."
                )
            client.check_task_write_capability()
            existing = _existing_task(client, task, key)
            if existing:
                return self._record(
                    key, "delivered", "Verified on source server", existing
                )
            # Persist before sending. A process crash leaves a recoverable uncertain row.
            self._record(
                key, "uncertain", "Delivery may be in flight; reconcile before retry"
            )
            attempted_write = True
            try:
                client.conditional_create_task(task, f"{IDENTIFIER_SYSTEM}|{key}")
            except FHIRClientError:
                # It may have committed before a timeout, 500, or later auth failure.
                existing = _existing_task(client, task, key)
                if existing:
                    return self._record(
                        key,
                        "delivered",
                        "Reconciled after write response failure",
                        existing,
                    )
                raise
            existing = _existing_task(client, task, key)
            if not existing:
                raise FHIRResponseError(
                    client.base_url,
                    "Task not visible after create; delivery is unconfirmed",
                )
            return self._record(key, "delivered", "Verified on source server", existing)
        except (
            FHIRClientError,
            ReviewGateError,
            OSError,
            ValueError,
            TypeError,
            AttributeError,
        ) as error:
            if isinstance(error, FHIRRetryLaterError):
                with self._connect() as db:
                    db.execute(
                        "INSERT OR REPLACE INTO cooldowns VALUES (?, ?)",
                        (client.base_url, time.time() + error.retry_after),
                    )
            # Details deliberately exclude remote bodies, URLs, tokens, and patient data.
            state = "uncertain" if attempted_write else "needs_attention"
            detail = (
                str(error)
                if isinstance(error, (FHIRClientError, ReviewGateError))
                else type(error).__name__
            )
            return self._record(
                key,
                state,
                detail
                + " Human follow-up required; replay the SAME saved review after recovery.",
            )

    def deliver_batch(self, keys, client):
        # Each key is a separate human-reviewed single-referral event, never a
        # multi-ServiceRequest parser input or an all-or-nothing FHIR transaction.
        results = []
        for key in keys:
            try:
                results.append(self.deliver(key, client))
            except ReviewGateError:
                results.append(
                    {
                        "review_id": key,
                        "state": "needs_attention",
                        "detail": "Invalid delivery key or destination; human follow-up required.",
                    }
                )
        return results
