"""Explicit replay/status CLI. Never invents or changes a human decision."""

import argparse
import json
import sys
import sqlite3

from src.fhir_client import FHIRClient, FHIRClientError
from src.writeback import DEFAULT_OUTBOX, ReviewOutbox
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outbox", type=Path, default=DEFAULT_OUTBOX)
    parser.add_argument(
        "--review-id",
        action="append",
        help="Saved review id to deliver; repeat for a batch.",
    )
    parser.add_argument(
        "--retry-pending",
        action="store_true",
        help="Explicitly replay all undelivered saved reviews for the configured server.",
    )
    args = parser.parse_args(argv)
    try:
        outbox = ReviewOutbox(args.outbox)
        if not args.review_id and not args.retry_pending:
            print(json.dumps(outbox.list(), indent=2))
            return 0
        client = FHIRClient()
        keys = args.review_id or [
            r["review_id"]
            for r in outbox.list()
            if r["state"] != "delivered" and r["base_url"] == client.base_url
        ]
        results = outbox.deliver_batch(keys, client)
        print(json.dumps(results, indent=2))
        return 0 if all(r["state"] == "delivered" for r in results) else 1
    except (FHIRClientError, OSError, sqlite3.Error) as error:
        print(
            f"Delivery unavailable: {type(error).__name__}. Local reviews remain saved.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
