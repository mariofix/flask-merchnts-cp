"""Async tests for flask_merchants Quart compatibility."""

import json
import pytest
import pytest_asyncio

from quart import Quart
from flask_merchants import FlaskMerchants


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def quart_app():
    """Quart app with FlaskMerchants (async blueprint)."""
    app = Quart(__name__)
    app.config["TESTING"] = True
    app.config["MERCHANTS_WEBHOOK_SECRET"] = None
    ext = FlaskMerchants(app)
    app.extensions["merchants_ext"] = ext
    return app


@pytest.fixture
def quart_ext(quart_app):
    return quart_app.extensions["merchants_ext"]


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_quart_checkout_json(quart_app):
    """POST /checkout with JSON body returns session_id and redirect_url."""
    async with quart_app.test_client() as client:
        resp = await client.post(
            "/merchants/checkout",
            json={"amount": "9.99", "currency": "USD"},
        )
        assert resp.status_code == 200
        data = await resp.get_json()
        assert "session_id" in data
        assert "redirect_url" in data


@pytest.mark.asyncio
async def test_quart_checkout_stores_session(quart_app, quart_ext):
    """Checkout stores the session in the in-memory store."""
    async with quart_app.test_client() as client:
        resp = await client.post(
            "/merchants/checkout",
            json={"amount": "5.00", "currency": "EUR"},
        )
        data = await resp.get_json()
        session_id = data["session_id"]

    stored = quart_ext.get_session(session_id)
    assert stored is not None
    assert stored["state"] == "pending"
    assert stored["currency"] == "EUR"


@pytest.mark.asyncio
async def test_quart_checkout_get_redirect(quart_app):
    """GET /checkout (non-JSON) redirects to the provider URL."""
    async with quart_app.test_client() as client:
        resp = await client.get("/merchants/checkout")
        assert resp.status_code == 302
        location = resp.headers.get("Location", "")
        assert "dummy-pay.example.com" in location


# ---------------------------------------------------------------------------
# Success / cancel
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_quart_success_view(quart_app):
    """GET /success returns status=success JSON."""
    async with quart_app.test_client() as client:
        resp = await client.get("/merchants/success")
        assert resp.status_code == 200
        data = await resp.get_json()
        assert data["status"] == "success"


@pytest.mark.asyncio
async def test_quart_cancel_view(quart_app):
    """GET /cancel returns status=cancelled JSON."""
    async with quart_app.test_client() as client:
        resp = await client.get("/merchants/cancel")
        assert resp.status_code == 200
        data = await resp.get_json()
        assert data["status"] == "cancelled"


# ---------------------------------------------------------------------------
# Payment status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_quart_payment_status(quart_app, quart_ext):
    """GET /status/<id> fetches live state and updates the store."""
    async with quart_app.test_client() as client:
        resp = await client.post(
            "/merchants/checkout",
            json={"amount": "1.00", "currency": "USD"},
        )
        data = await resp.get_json()
        session_id = data["session_id"]

        status_resp = await client.get(f"/merchants/status/{session_id}")
        assert status_resp.status_code == 200
        status_data = await status_resp.get_json()
        assert "state" in status_data
        assert status_data["payment_id"] == session_id

    # Store should be updated
    stored = quart_ext.get_session(session_id)
    assert stored["state"] == status_data["state"]


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_quart_webhook_no_secret(quart_app):
    """POST /webhook with no secret set processes the event."""
    payload = json.dumps({
        "payment_id": "pay_test",
        "event_type": "payment.succeeded",
        "event_id": "evt_001",
    }).encode()

    async with quart_app.test_client() as client:
        resp = await client.post(
            "/merchants/webhook",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        data = await resp.get_json()
        assert data["received"] is True


@pytest.mark.asyncio
async def test_quart_webhook_invalid_signature(quart_app):
    """POST /webhook with wrong signature returns 400."""
    app = Quart(__name__)
    app.config["TESTING"] = True
    app.config["MERCHANTS_WEBHOOK_SECRET"] = "my-secret"
    FlaskMerchants(app)

    payload = b'{"payment_id": "x"}'

    async with app.test_client() as client:
        resp = await client.post(
            "/merchants/webhook",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-Merchants-Signature": "sha256=badsig",
            },
        )
        assert resp.status_code == 400
        data = await resp.get_json()
        assert "invalid signature" in data["error"]


@pytest.mark.asyncio
async def test_quart_webhook_malformed(quart_app):
    """POST /webhook with empty payload is processed (DummyProvider is lenient)."""
    async with quart_app.test_client() as client:
        resp = await client.post(
            "/merchants/webhook",
            data=b"",
            headers={"Content-Type": "application/octet-stream"},
        )
        # DummyProvider synthesises an event for any payload, so 200 is expected
        assert resp.status_code == 200
        data = await resp.get_json()
        assert data["received"] is True


# ---------------------------------------------------------------------------
# Blueprint detection
# ---------------------------------------------------------------------------

def test_quart_blueprint_selected():
    """FlaskMerchants selects the async blueprint for Quart apps."""
    app = Quart(__name__)
    app.config["TESTING"] = True
    ext = FlaskMerchants(app)

    rules = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/merchants/checkout" in rules
    assert "/merchants/webhook" in rules
