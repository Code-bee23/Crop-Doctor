import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import db

client = TestClient(app)


def test_review_dashboard_html():
    """Verify HTML review page renders successfully."""
    response = client.get("/reviews")
    assert response.status_code == 200
    assert "Crop Doctor on WhatsApp" in response.text
    assert "Expert Review Dashboard" in response.text


def test_get_api_cases():
    """Verify JSON endpoint returns case records."""
    response = client.get("/api/cases")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_submit_review_audit():
    """Verify submitting an agricultural audit updates the case record."""
    # Create a mock case in DB first
    case = await db.create_case({
        "wa_phone": "919988776655",
        "crop": "chilli",
        "answer_text": "Spray Diafenthiuron 50% WP @ 1.25 g per litre",
        "status": "completed"
    })
    case_id = case["id"]

    # Submit audit form
    form_data = {
        "case_id": case_id,
        "reviewer": "Dr. Ramesh (KVK Warangal)",
        "verdict": "correct",
        "note": "Accurate dose according to PJTSAU guide"
    }
    response = client.post("/reviews/audit", data=form_data, follow_redirects=False)
    assert response.status_code == 303  # HTTP 303 See Other redirect to /reviews

    # Verify case has the review attached
    cases = client.get("/api/cases").json()
    matched = next((c for c in cases if c["id"] == case_id), None)
    assert matched is not None
    assert "reviews" in matched
    assert matched["reviews"][0]["verdict"] == "correct"
    assert matched["reviews"][0]["reviewer"] == "Dr. Ramesh (KVK Warangal)"


def test_submit_invalid_review_verdict():
    """Verify invalid verdict value is rejected with 400."""
    form_data = {
        "case_id": "mock_id",
        "reviewer": "Tester",
        "verdict": "completely_invalid_verdict",
        "note": "test"
    }
    response = client.post("/reviews/audit", data=form_data)
    assert response.status_code == 400

