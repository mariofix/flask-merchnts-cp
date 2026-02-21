"""Tests for the webhook endpoint."""

import hashlib
import hmac
import json

import pytest
from flask import Flask

from flask_merchants import FlaskMerchants


def _sign(payload: bytes, secret: str) -> str:
    """Compute HMAC-SHA256 signature matching the merchants SDK format."""
    mac = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={mac}"


@pytest.fixture
def webhook_app():
    """App with MERCHANTS_WEBHOOK_SECRET configured."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["MERCHANTS_WEBHOOK_SECRET"] = "test-webhook-secret"
    FlaskMerchants(app)
    return app


@pytest.fixture
def webhook_client(webhook_app):
    return webhook_app.test_client()


# ---------------------------------------------------------------------------
# Without signature verification
# ---------------------------------------------------------------------------


def test_webhook_no_secret(client):
    """Webhook endpoint accepts requests when no secret is configured."""
    payload = json.dumps(
        {
            "payment_id": "dummy_pay_abc",
            "event_type": "payment.succeeded",
            "event_id": "dummy_evt_xyz",
        }
    ).encode()

    resp = client.post(
        "/merchants/webhook",
        data=payload,
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["received"] is True
    assert data["payment_id"] == "dummy_pay_abc"
    assert data["event_type"] == "payment.succeeded"


def test_webhook_updates_store(client, ext):
    """Webhook endpoint updates the stored state for a known payment."""
    # First create a checkout session
    resp = client.post("/merchants/checkout", json={"amount": "1.00", "currency": "USD"})
    session_id = resp.get_json()["session_id"]

    payload = json.dumps(
        {
            "payment_id": session_id,
            "event_type": "payment.succeeded",
            "event_id": "evt_001",
        }
    ).encode()

    client.post(
        "/merchants/webhook",
        data=payload,
        content_type="application/json",
    )

    stored = ext.get_session(session_id)
    assert stored["state"] == "succeeded"


# ---------------------------------------------------------------------------
# With signature verification
# ---------------------------------------------------------------------------


def test_webhook_valid_signature(webhook_client):
    """Valid HMAC signature is accepted."""
    payload = json.dumps({"payment_id": "pay_1", "event_type": "payment.succeeded"}).encode()
    sig = _sign(payload, "test-webhook-secret")

    resp = webhook_client.post(
        "/merchants/webhook",
        data=payload,
        content_type="application/json",
        headers={"X-Merchants-Signature": sig},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["received"] is True


def test_webhook_invalid_signature(webhook_client):
    """Invalid signature returns 400."""
    payload = json.dumps({"payment_id": "pay_1"}).encode()

    resp = webhook_client.post(
        "/merchants/webhook",
        data=payload,
        content_type="application/json",
        headers={"X-Merchants-Signature": "sha256=badsignature"},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert "invalid signature" in data["error"]


def test_webhook_missing_signature_with_secret(webhook_client):
    """Missing signature when secret is configured returns 400."""
    payload = json.dumps({"payment_id": "pay_1"}).encode()

    resp = webhook_client.post(
        "/merchants/webhook",
        data=payload,
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_webhook_malformed_payload(client):
    """Non-JSON payload is handled gracefully."""
    resp = client.post(
        "/merchants/webhook",
        data=b"not-json",
        content_type="text/plain",
    )
    # DummyProvider's parse_webhook handles non-JSON by using defaults
    assert resp.status_code in (200, 400)
