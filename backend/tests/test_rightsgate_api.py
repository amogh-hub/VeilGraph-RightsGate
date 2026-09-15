"""HTTP boundary tests for RightsGate's versioned, non-authorizing contracts."""

from __future__ import annotations

import io
import hashlib

from fastapi.testclient import TestClient
from PIL import Image


def request_payload() -> dict:
    asset_sha256 = "a" * 64
    return {
        "schema": "veilgraph.rightsgate.assessment-request.v1",
        "idempotency_key": "request.demo-001",
        "asset_ir": {
            "schema": "veilgraph.rightsgate.asset-ir.v1",
            "asset": {
                "asset_id": "asset.demo-001",
                "sha256": asset_sha256,
                "media_kind": "IMAGE",
                "media_type": "image/png",
                "size_bytes": 4096,
                "original_filename": "campaign.png",
                "width": 1920,
                "height": 1080,
            },
            "representations": [
                {
                    "representation_id": "representation.original-001",
                    "kind": "ORIGINAL",
                    "sha256": asset_sha256,
                    "media_type": "image/png",
                    "size_bytes": 4096,
                    "locator": {"kind": "WHOLE_ASSET"},
                }
            ],
        },
        "context": {
            "policy_id": "policy.publication",
            "policy_version": "2026.09.1",
            "intended_use": "Public advertising campaign",
            "channel": "web",
            "audience": "general",
            "territories": ["IN"],
        },
        "requested_dimensions": [
            "PROVENANCE",
            "RIGHTS_EXPOSURE",
            "DEPLOYMENT_READINESS",
        ],
    }


def test_contract_bundle_declares_implemented_contracts_without_detector_claims(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/rightsgate/contracts")
    assert response.status_code == 200
    body = response.json()
    assert body["contract_status"] == "IMPLEMENTED"
    assert body["execution_status"] == "IMPLEMENTED"
    assert body["detector_status"] == "PARTIAL"
    assert set(body["schemas"]) == {
        "veilgraph.rightsgate.asset-ir.v1",
        "veilgraph.rightsgate.assessment-request.v1",
        "veilgraph.rightsgate.asset-exposure-graph.v1",
        "veilgraph.rightsgate.assessment.v1",
        "veilgraph.rightsgate.rights-reference-registry.v1",
        "veilgraph.rightsgate.licence-registry.v1",
        "veilgraph.rightsgate.publication-policy.v1",
        "veilgraph.rightsgate.cms-decision-request.v1",
        "veilgraph.rightsgate.cms-decision-receipt.v1",
    }


def test_request_validation_is_deterministic_and_does_not_start_assessment(
    client: TestClient,
) -> None:
    payload = request_payload()
    first = client.post("/api/v1/rightsgate/requests/validate", json=payload)
    second = client.post("/api/v1/rightsgate/requests/validate", json=payload)

    assert first.status_code == 200
    assert first.json() == second.json()
    assert first.json()["assessment_started"] is False
    assert len(first.json()["request_sha256"]) == 64


def test_request_validation_rejects_incomplete_dimension_set(client: TestClient) -> None:
    payload = request_payload()
    payload["requested_dimensions"] = ["PROVENANCE"]

    response = client.post("/api/v1/rightsgate/requests/validate", json=payload)
    assert response.status_code == 422
    assert "each challenge dimension" in response.text


def test_openapi_exposes_rightsgate_contract_boundary(client: TestClient) -> None:
    document = client.get("/openapi.json").json()
    assert "/api/v1/rightsgate/contracts" in document["paths"]
    assert "/api/v1/rightsgate/requests/validate" in document["paths"]
    assert "/api/v1/rightsgate/assessments/validate" in document["paths"]
    assert "/api/v1/rightsgate/provenance/c2pa" in document["paths"]
    assert "/api/v1/rightsgate/rights/references/image" in document["paths"]
    assert "/api/v1/rightsgate/assessments" in document["paths"]
    assert "/api/v1/rightsgate/assessments/{idempotency_key}" in document["paths"]


def test_c2pa_endpoint_inspects_unsigned_image_without_claiming_human_authorship(
    client: TestClient,
) -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), color=(255, 255, 255)).save(buffer, format="PNG")

    response = client.post(
        "/api/v1/rightsgate/provenance/c2pa",
        files={"file": ("unsigned.png", buffer.getvalue(), "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["component"]["state"] == "AVAILABLE"
    assert body["assessment"]["verdict"] == "UNKNOWN"
    assert "not evidence of human authorship" in body["assessment"]["limitations"][0]


def test_c2pa_endpoint_rejects_unrecognized_input(client: TestClient) -> None:
    response = client.post(
        "/api/v1/rightsgate/provenance/c2pa",
        files={"file": ("asset.bin", b"not media", "application/octet-stream")},
    )
    assert response.status_code == 400


def test_image_reference_endpoint_derives_byte_bound_record(client: TestClient) -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (4, 3), color=(10, 20, 30)).save(buffer, format="PNG")
    data = buffer.getvalue()
    response = client.post(
        "/api/v1/rightsgate/rights/references/image",
        data={
            "reference_id": "reference.demo-001",
            "kind": "COPYRIGHTED_WORK",
            "title": "Demo work",
            "rights_holder": "Demo rights holder",
            "source_record_id": "rights-record.demo-001",
        },
        files={"file": ("reference.png", data, "image/png")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["sha256"] == hashlib.sha256(data).hexdigest()
    assert len(response.json()["dhash"]) == 16
