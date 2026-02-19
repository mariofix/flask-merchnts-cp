"""Tests for the checkout, success, cancel and status views."""

import json

import pytest


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------

def test_checkout_json_response(client):
    """POST /merchants/checkout with JSON body returns session data."""
    resp = client.post(
        "/merchants/checkout",
        json={"amount": "9.99", "currency": "EUR"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "session_id" in data
    assert "redirect_url" in data
    assert data["session_id"].startswith("dummy_sess_")


def test_checkout_stores_session(client, ext):
    """Checkout endpoint persists the session in the store."""
    resp = client.post(
        "/merchants/checkout",
        json={"amount": "5.00", "currency": "USD"},
    )
    session_id = resp.get_json()["session_id"]
    stored = ext.get_session(session_id)
    assert stored is not None
    assert stored["amount"] == "5.00"
    assert stored["currency"] == "USD"
    assert stored["state"] == "pending"


def test_checkout_get_redirect(client):
    """GET /merchants/checkout redirects to the provider URL."""
    resp = client.get("/merchants/checkout")
    assert resp.status_code == 302
    assert "dummy-pay.example.com" in resp.headers["Location"]


def test_checkout_default_amount(client):
    """Checkout uses 1.00 USD as default when no amount/currency provided."""
    resp = client.post("/merchants/checkout", json={})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["redirect_url"].endswith("amount=1.00&currency=USD")


def test_checkout_with_metadata(client, ext):
    """Metadata is stored alongside the checkout session."""
    resp = client.post(
        "/merchants/checkout",
        json={"amount": "20.00", "currency": "GBP", "metadata": {"order_id": "ord_1"}},
    )
    session_id = resp.get_json()["session_id"]
    stored = ext.get_session(session_id)
    assert stored["metadata"] == {"order_id": "ord_1"}


# ---------------------------------------------------------------------------
# Success / cancel
# ---------------------------------------------------------------------------

def test_success_view_no_payment_id(client):
    resp = client.get("/merchants/success")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["payment_id"] is None


def test_success_view_with_payment_id(client, ext):
    # Create a session first
    resp = client.post("/merchants/checkout", json={"amount": "1.00", "currency": "USD"})
    session_id = resp.get_json()["session_id"]

    resp = client.get(f"/merchants/success?payment_id={session_id}")
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["payment_id"] == session_id
    assert data["stored"]["session_id"] == session_id


def test_cancel_view(client):
    resp = client.get("/merchants/cancel")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "cancelled"


# ---------------------------------------------------------------------------
# Payment status
# ---------------------------------------------------------------------------

def test_payment_status_returns_state(client, ext):
    """Status endpoint returns state info from the provider."""
    resp = client.post("/merchants/checkout", json={"amount": "1.00", "currency": "USD"})
    session_id = resp.get_json()["session_id"]

    resp = client.get(f"/merchants/status/{session_id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["payment_id"] == session_id
    assert data["provider"] == "dummy"
    assert "state" in data
    assert "is_final" in data
    assert "is_success" in data


def test_payment_status_updates_store(client, ext):
    """Status endpoint updates the stored state."""
    from merchants import PaymentState
    from merchants.providers.dummy import DummyProvider

    # Use a provider that always returns SUCCEEDED
    from flask import Flask
    from flask_merchants import Merchants

    test_app = Flask(__name__)
    test_app.config["TESTING"] = True
    provider = DummyProvider(always_state=PaymentState.SUCCEEDED)
    test_ext = Merchants(test_app, provider=provider)

    with test_app.test_client() as tc:
        # Create session
        resp = tc.post("/merchants/checkout", json={"amount": "1.00", "currency": "USD"})
        session_id = resp.get_json()["session_id"]

        # Check status – should update store to succeeded
        tc.get(f"/merchants/status/{session_id}")
        stored = test_ext.get_session(session_id)
        assert stored["state"] == "succeeded"
