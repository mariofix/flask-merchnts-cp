"""Tests for the Flask-Admin contrib views."""

import pytest
from flask import Flask
from flask_admin import Admin

from flask_merchants import FlaskMerchants
from flask_merchants.contrib.admin import PaymentView


@pytest.fixture
def admin_app():
    """Flask app with Flask-Admin and PaymentView registered."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"

    ext = FlaskMerchants(app)

    admin = Admin(app, name="Test Admin")
    admin.add_view(PaymentView(ext, name="Payments", endpoint="payments"))

    app.extensions["merchants_ext_for_test"] = ext
    return app


@pytest.fixture
def admin_client(admin_app):
    return admin_app.test_client()


@pytest.fixture
def admin_ext(admin_app):
    return admin_app.extensions["merchants_ext_for_test"]


# ---------------------------------------------------------------------------
# List view
# ---------------------------------------------------------------------------

def test_payments_list_empty(admin_client):
    """Admin payments list renders with no payments."""
    resp = admin_client.get("/admin/payments/")
    assert resp.status_code == 200
    assert b"No payments recorded" in resp.data


def test_payments_list_shows_sessions(admin_client, admin_ext):
    """Admin list displays checkout sessions that have been stored."""
    # Create a checkout
    admin_client.post(
        "/merchants/checkout",
        json={"amount": "25.00", "currency": "USD"},
    )

    resp = admin_client.get("/admin/payments/")
    assert resp.status_code == 200
    assert b"dummy_sess_" in resp.data


# ---------------------------------------------------------------------------
# Update state
# ---------------------------------------------------------------------------

def test_update_state_success(admin_client, admin_ext):
    """Posting a valid update changes the stored state."""
    # Create a checkout to get a payment ID
    resp = admin_client.post(
        "/merchants/checkout",
        json={"amount": "10.00", "currency": "USD"},
    )
    session_id = resp.get_json()["session_id"]

    update_resp = admin_client.post(
        "/admin/payments/update",
        data={"payment_id": session_id, "state": "succeeded"},
    )
    # Should redirect back to list
    assert update_resp.status_code == 302

    stored = admin_ext.get_session(session_id)
    assert stored["state"] == "succeeded"


def test_update_state_unknown_id(admin_client):
    """Posting an unknown payment ID flashes a 'not found' message."""
    resp = admin_client.post(
        "/admin/payments/update",
        data={"payment_id": "does-not-exist", "state": "failed"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"not found" in resp.data


def test_update_state_missing_fields(admin_client):
    """Submitting an empty form flashes an error."""
    resp = admin_client.post(
        "/admin/payments/update",
        data={},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Invalid" in resp.data


# ---------------------------------------------------------------------------
# PaymentView instantiation
# ---------------------------------------------------------------------------

def test_refund_action_success(admin_client, admin_ext):
    """Refund action marks the payment as refunded."""
    resp = admin_client.post(
        "/merchants/checkout",
        json={"amount": "10.00", "currency": "USD"},
    )
    session_id = resp.get_json()["session_id"]

    refund_resp = admin_client.post(
        "/admin/payments/refund",
        data={"payment_id": session_id},
    )
    assert refund_resp.status_code == 302

    stored = admin_ext.get_session(session_id)
    assert stored["state"] == "refunded"


def test_refund_action_unknown_id(admin_client):
    """Refund of an unknown payment ID flashes a 'not found' message."""
    resp = admin_client.post(
        "/admin/payments/refund",
        data={"payment_id": "does-not-exist"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"not found" in resp.data


def test_cancel_action_success(admin_client, admin_ext):
    """Cancel action marks the payment as cancelled."""
    resp = admin_client.post(
        "/merchants/checkout",
        json={"amount": "5.00", "currency": "EUR"},
    )
    session_id = resp.get_json()["session_id"]

    cancel_resp = admin_client.post(
        "/admin/payments/cancel",
        data={"payment_id": session_id},
    )
    assert cancel_resp.status_code == 302

    stored = admin_ext.get_session(session_id)
    assert stored["state"] == "cancelled"


def test_cancel_action_unknown_id(admin_client):
    """Cancel of an unknown payment ID flashes a 'not found' message."""
    resp = admin_client.post(
        "/admin/payments/cancel",
        data={"payment_id": "does-not-exist"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"not found" in resp.data


def test_refund_missing_payment_id(admin_client):
    """Refund with no payment_id flashes an invalid message."""
    resp = admin_client.post(
        "/admin/payments/refund",
        data={},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Invalid" in resp.data


def test_cancel_missing_payment_id(admin_client):
    """Cancel with no payment_id flashes an invalid message."""
    resp = admin_client.post(
        "/admin/payments/cancel",
        data={},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Invalid" in resp.data
    """PaymentView is a subclass of Flask-Admin BaseView."""
    from flask_admin import BaseView

    assert issubclass(PaymentView, BaseView)


def test_payment_view_requires_ext():
    """PaymentView is created with the extension instance."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "s"
    ext = FlaskMerchants(app)
    view = PaymentView(ext, name="P", endpoint="p")
    assert view._ext is ext
