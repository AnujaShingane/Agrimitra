from io import BytesIO
from types import SimpleNamespace
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from google.genai import errors as genai_errors
from PIL import Image

import main


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main.limiter, "enabled", False)
    with TestClient(main.app) as test_client:
        yield test_client


def _make_leaf_image() -> bytes:
    image = Image.new("RGB", (100, 100), color=(70, 150, 60))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _analysis() -> dict:
    return {
        "plant_name": "Tomato",
        "plant_identification_note": "The leaf appears consistent with tomato.",
        "possible_disease": "Possible early blight",
        "diagnosis_status": "possible",
        "observed_symptoms": ["Dark spots on the leaf"],
        "explanation": "The visible spots may fit an early fungal problem.",
        "alternative_causes": ["Other leaf spot diseases can look similar."],
        "severity": "moderate",
        "treatment": ["Remove badly affected leaves and monitor nearby plants."],
        "prevention": ["Avoid wetting leaves while watering."],
        "confidence_note": "A photo cannot confirm the cause; inspect more plants.",
        "when_to_consult_an_expert": "Ask a local agriculture expert if symptoms spread.",
    }


def _install_fake_gemini(monkeypatch, output_text: str, captured: dict | None = None):
    class FakeModels:
        def generate_content(self, **kwargs):
            if captured is not None:
                captured.update(kwargs)
            return SimpleNamespace(text=output_text)

    class FakeGemini:
        def __init__(self, **kwargs):
            if captured is not None:
                captured["client_options"] = kwargs
            self.models = FakeModels()

    monkeypatch.setattr(main.genai, "Client", FakeGemini)


def _post_scan(client, **data):
    form = {
        "plant": "Tomato",
        "noticed_when": "A few days ago",
        "spreading": "Not sure",
        "description": "It rained this week.",
    }
    form.update(data)
    return client.post(
        "/api/scan?lang=en",
        files={"file": ("leaf.png", _make_leaf_image(), "image/png")},
        data=form,
    )


def test_scan_sends_image_and_farmer_context_to_gemini_and_returns_structured_result(
    client, monkeypatch
):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    captured = {}
    _install_fake_gemini(monkeypatch, json.dumps(_analysis()), captured)

    response = _post_scan(
        client,
        observations=["Black or brown spots", "Yellow leaves"],
        additional_symptoms="Some lower leaves are soft.",
    )

    assert response.status_code == 200
    assert response.json()["analysis"] == _analysis()
    assert captured["model"] == "gemini-2.5-flash"
    image_part, context = captured["contents"]
    assert "Plant name provided by farmer: Tomato" in context
    assert "Black or brown spots, Yellow leaves" in context
    assert "A few days ago" in context
    assert "Not sure" in context
    assert "Some lower leaves are soft." in context
    assert image_part.inline_data.data == _make_leaf_image()
    assert captured["config"].response_mime_type == "application/json"
    assert captured["config"].response_schema is main.LeafScanAnalysis
    assert "additionalProperties" not in main.LeafScanAnalysis.model_json_schema()
    instructions = captured["config"].system_instruction
    assert 'When the status is\n"possible" or "uncertain"' in instructions
    assert "Do not call symptoms" in instructions
    assert "photo alone cannot confirm the cause" in instructions
    assert captured["client_options"]["api_key"] == "test-key"
    http_options = captured["client_options"]["http_options"]
    assert http_options.api_version == "v1beta"
    assert http_options.retry_options.attempts == 3
    assert http_options.retry_options.initial_delay == 1
    assert http_options.retry_options.max_delay == 3
    assert http_options.retry_options.http_status_codes == [
        408, 429, 500, 502, 503, 504
    ]


def test_scan_requires_plant_name(client):
    response = client.post(
        "/api/scan",
        files={"file": ("leaf.png", _make_leaf_image(), "image/png")},
    )
    assert response.status_code == 422


def test_scan_rejects_invalid_image(client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    response = client.post(
        "/api/scan",
        data={"plant": "Tomato"},
        files={"file": ("leaf.png", b"not an image", "image/png")},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded file is not a valid image."


def test_scan_rejects_images_over_10mb(client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    response = client.post(
        "/api/scan",
        data={"plant": "Tomato"},
        files={"file": ("leaf.png", b"x" * (10 * 1024 * 1024 + 1), "image/png")},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Image must be 10MB or smaller."


def test_scan_reports_missing_gemini_key(client, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    response = _post_scan(client)
    assert response.status_code == 503
    assert "GEMINI_API_KEY" in response.json()["detail"]


def test_scan_reports_invalid_structured_gemini_response(client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    _install_fake_gemini(monkeypatch, '{"possible_disease": "incomplete"}')
    response = _post_scan(client)
    assert response.status_code == 502
    assert "invalid leaf analysis" in response.json()["detail"]


def test_scan_ignores_unexpected_fields_in_gemini_response(client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    analysis = _analysis()
    analysis["unexpected_field"] = "must not be returned"
    _install_fake_gemini(
        monkeypatch, f"```json\n{json.dumps(analysis)}\n```"
    )

    response = _post_scan(client)

    assert response.status_code == 200
    assert response.json()["analysis"] == _analysis()


def test_scan_reports_gemini_connection_failure(client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    class FailingGemini:
        def __init__(self, **kwargs):
            self.models = self

        def generate_content(self, **kwargs):
            raise httpx.ConnectError(
                "Gemini connection failed",
                request=httpx.Request("POST", "https://generativelanguage.googleapis.com"),
            )

    monkeypatch.setattr(main.genai, "Client", FailingGemini)
    response = _post_scan(client)
    assert response.status_code == 503
    assert "temporarily unavailable" in response.json()["detail"]


def test_scan_reports_gemini_timeout(client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    class FailingGemini:
        def __init__(self, **kwargs):
            self.models = self

        def generate_content(self, **kwargs):
            raise httpx.ReadTimeout(
                "Gemini timed out",
                request=httpx.Request("POST", "https://generativelanguage.googleapis.com"),
            )

    monkeypatch.setattr(main.genai, "Client", FailingGemini)
    response = _post_scan(client)
    assert response.status_code == 504
    assert "timed out" in response.json()["detail"]


def test_scan_reports_gemini_quota_error(client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    class FailingGemini:
        def __init__(self, **kwargs):
            self.models = self

        def generate_content(self, **kwargs):
            raise genai_errors.APIError(
                code=429,
                response_json={"error": {"message": "quota exceeded"}},
            )

    monkeypatch.setattr(main.genai, "Client", FailingGemini)
    response = _post_scan(client)
    assert response.status_code == 503
    assert "quota" in response.json()["detail"].lower()


def test_scan_reports_gemini_temporarily_unavailable(client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    class FailingGemini:
        def __init__(self, **kwargs):
            self.models = self

        def generate_content(self, **kwargs):
            raise genai_errors.APIError(
                code=503,
                response_json={
                    "error": {
                        "status": "UNAVAILABLE",
                        "message": "Model is experiencing high demand.",
                    }
                },
            )

    monkeypatch.setattr(main.genai, "Client", FailingGemini)
    response = _post_scan(client)

    assert response.status_code == 503
    assert "temporarily busy" in response.json()["detail"]


def test_scan_logs_gemini_bad_request_reason_without_exposing_it_to_client(
    client, monkeypatch
):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    logged = {}

    class CapturingLogger:
        def error(self, event, **kwargs):
            logged.update(event=event, **kwargs)

    class FailingGemini:
        def __init__(self, **kwargs):
            self.models = self

        def generate_content(self, **kwargs):
            raise genai_errors.APIError(
                code=400,
                response_json={
                    "error": {
                        "status": "INVALID_ARGUMENT",
                        "message": "The selected model does not support this request.",
                    }
                },
            )

    monkeypatch.setattr(main, "logger", CapturingLogger())
    monkeypatch.setattr(main.genai, "Client", FailingGemini)

    response = _post_scan(client)

    assert response.status_code == 502
    assert response.json()["detail"] == (
        "Leaf analysis could not be completed. Please try again later."
    )
    assert logged["status_code"] == 400
    assert logged["provider_status"] == "INVALID_ARGUMENT"
    assert logged["provider_error"] == (
        "The selected model does not support this request."
    )
