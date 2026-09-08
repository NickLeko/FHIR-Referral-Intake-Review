from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.models import HumanReviewDecision
from src.utils import load_json_file
from src.contracts import reviewed_output_contract_errors
from src.writeback import ReviewOutbox
from test_integration import MockFHIRServer, make_client


def button(app, label):
    return next(item for item in app.button if item.label == label)


def test_mock_review_override_gate_and_saved_contract(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.utils.review_history_output_path", lambda *args: tmp_path / "review.json"
    )
    app = AppTest.from_file(Path("app.py").resolve(), default_timeout=10).run()
    assert not app.exception
    app.radio(key="decision").set_value(HumanReviewDecision.CONFIRM_INCOMPLETE)
    button(app, "Generate reviewed handoff summary").click().run()
    assert app.error and not (tmp_path / "review.json").exists()
    app.text_area(key="review_note").input(
        "Mock reviewer found missing external paperwork"
    )
    button(app, "Generate reviewed handoff summary").click().run()
    assert not app.exception
    assert (
        reviewed_output_contract_errors(load_json_file(tmp_path / "review.json")) == []
    )


def test_live_ui_requires_submission_and_retries_saved_review(monkeypatch, tmp_path):
    server = MockFHIRServer()
    client = make_client(server)
    outbox = ReviewOutbox(tmp_path / "outbox.sqlite3")
    original_enqueue = outbox.enqueue
    monkeypatch.setattr(
        outbox,
        "enqueue",
        lambda payload, **kwargs: original_enqueue(
            payload, output_dir=tmp_path / "reviews", **kwargs
        ),
    )
    monkeypatch.setattr("src.fhir_client.FHIRClient", lambda: client)
    monkeypatch.setattr("src.writeback.ReviewOutbox", lambda: outbox)
    app = AppTest.from_file(Path("app.py").resolve(), default_timeout=10).run()
    app.radio[0].set_value("Live sandbox").run()
    next(t for t in app.text_input if t.label == "ServiceRequest ID").input("one")
    button(app, "Fetch referral").click().run()
    assert not app.exception and not server.tasks and not outbox.list()
    server.faults[("POST", "/fhir/Task")].extend([500] * 3)
    button(app, "Save review and record disposition on sandbox").click().run()
    assert not app.exception
    assert len(outbox.list()) == 1 and outbox.list()[0]["state"] == "uncertain"
    button(app, "Retry delivery of this saved review").click().run()
    assert not app.exception and len(outbox.list()) == len(server.tasks) == 1
    assert outbox.list()[0]["state"] == "delivered"
    assert button(app, "Save review and record disposition on sandbox").disabled


def test_failed_live_refetch_clears_previous_review_form(monkeypatch):
    server = MockFHIRServer()
    client = make_client(server)
    monkeypatch.setattr("src.fhir_client.FHIRClient", lambda: client)
    app = AppTest.from_file(Path("app.py").resolve(), default_timeout=10).run()
    app.radio[0].set_value("Live sandbox").run()
    next(t for t in app.text_input if t.label == "ServiceRequest ID").input("one")
    button(app, "Fetch referral").click().run()
    assert not app.exception
    server.faults[("GET", "/fhir/ServiceRequest/one")].extend([500] * 3)
    button(app, "Fetch referral").click().run()
    assert not app.exception and app.error
    assert not any(
        b.label == "Save review and record disposition on sandbox" for b in app.button
    )
