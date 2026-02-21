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


# ---------------------------------------------------------------------------
# Sync from provider
# ---------------------------------------------------------------------------

def test_sync_action_success(admin_client, admin_ext):
    """Sync action fetches live state from the provider and updates the store."""
    resp = admin_client.post(
        "/merchants/checkout",
        json={"amount": "1.00", "currency": "USD"},
    )
    session_id = resp.get_json()["session_id"]
    # State starts as pending
    assert admin_ext.get_session(session_id)["state"] == "pending"

    sync_resp = admin_client.post(
        "/admin/payments/sync",
        data={"payment_id": session_id},
    )
    assert sync_resp.status_code == 302

    # DummyProvider always returns a terminal state; store should be updated
    updated_state = admin_ext.get_session(session_id)["state"]
    assert updated_state != "pending"


def test_sync_action_unknown_id(admin_client):
    """Sync of an unknown payment ID flashes a failure message."""
    resp = admin_client.post(
        "/admin/payments/sync",
        data={"payment_id": "does-not-exist"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"not found" in resp.data


def test_sync_missing_payment_id(admin_client):
    """Sync with no payment_id flashes an invalid message."""
    resp = admin_client.post(
        "/admin/payments/sync",
        data={},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Invalid" in resp.data


# ---------------------------------------------------------------------------
# PaymentView class
# ---------------------------------------------------------------------------

def test_payment_view_is_base_view():
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


# ---------------------------------------------------------------------------
# Auto-registration via admin= parameter
# ---------------------------------------------------------------------------

@pytest.fixture
def auto_admin_app():
    """Flask app where admin views are auto-registered via admin= parameter."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"

    from flask_admin import Admin

    admin = Admin(app, name="Auto Admin")
    FlaskMerchants(app, admin=admin)
    return app


@pytest.fixture
def auto_admin_client(auto_admin_app):
    return auto_admin_app.test_client()


def test_auto_registration_payments_view(auto_admin_client):
    """Auto-registered PaymentView is accessible under /admin/merchants_payments/."""
    resp = auto_admin_client.get("/admin/merchants_payments/")
    assert resp.status_code == 200
    assert b"Payments" in resp.data


def test_auto_registration_providers_view(auto_admin_client):
    """Auto-registered ProvidersView is accessible under /admin/merchants_providers/."""
    resp = auto_admin_client.get("/admin/merchants_providers/")
    assert resp.status_code == 200
    assert b"Providers" in resp.data


def test_auto_registration_providers_shows_dummy(auto_admin_client):
    """ProvidersView lists the dummy provider registered by default."""
    resp = auto_admin_client.get("/admin/merchants_providers/")
    assert resp.status_code == 200
    assert b"dummy" in resp.data


def test_providers_view_is_base_view():
    """ProvidersView is a subclass of Flask-Admin BaseView."""
    from flask_admin import BaseView
    from flask_merchants.contrib.admin import ProvidersView

    assert issubclass(ProvidersView, BaseView)


def test_register_admin_views_function():
    """register_admin_views adds PaymentView and ProvidersView under Merchants category."""
    from flask_admin import Admin
    from flask_merchants.contrib.admin import register_admin_views

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "s"
    admin = Admin(app, name="Test")
    ext = FlaskMerchants(app)
    register_admin_views(admin, ext)

    # Both views should be registered; verify via test client
    with app.test_client() as client:
        assert client.get("/admin/merchants_payments/").status_code == 200
        assert client.get("/admin/merchants_providers/").status_code == 200


def test_init_app_admin_parameter():
    """admin= passed to init_app is used for auto-registration."""
    from flask_admin import Admin

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "s"

    admin = Admin(app, name="Test")
    ext = FlaskMerchants()
    ext.init_app(app, admin=admin)

    with app.test_client() as client:
        assert client.get("/admin/merchants_payments/").status_code == 200
        assert client.get("/admin/merchants_providers/").status_code == 200


# ---------------------------------------------------------------------------
# _mask_secret helper
# ---------------------------------------------------------------------------

def test_mask_secret_long_value():
    """Long secrets show first 5 chars, ellipsis, and last char."""
    from flask_merchants.contrib.admin import _mask_secret

    result = _mask_secret("sk_test_1234567890")
    assert result == "sk_te…0"


def test_mask_secret_short_value():
    """Short secrets (<=6 chars) are fully masked."""
    from flask_merchants.contrib.admin import _mask_secret

    assert _mask_secret("short") == "***"
    assert _mask_secret("123456") == "***"


def test_mask_secret_exactly_seven_chars():
    """Values with exactly 7 chars return first 5 + ellipsis + last 1."""
    from flask_merchants.contrib.admin import _mask_secret

    result = _mask_secret("1234567")
    assert result == "12345…7"


# ---------------------------------------------------------------------------
# _get_auth_info helper
# ---------------------------------------------------------------------------

def test_get_auth_info_none():
    """None auth returns unauthenticated descriptor."""
    from flask_merchants.contrib.admin import _get_auth_info

    info = _get_auth_info(None)
    assert info["type"] == "None"
    assert info["masked_value"] == "—"


def test_get_auth_info_api_key():
    """ApiKeyAuth returns masked api_key and correct header."""
    from merchants.auth import ApiKeyAuth
    from flask_merchants.contrib.admin import _get_auth_info

    auth = ApiKeyAuth(api_key="sk_test_abcdefghij", header="X-Api-Key")
    info = _get_auth_info(auth)
    assert info["type"] == "ApiKeyAuth"
    assert info["header"] == "X-Api-Key"
    assert info["masked_value"] == "sk_te…j"


def test_get_auth_info_token_auth():
    """TokenAuth returns masked token and correct header."""
    from merchants.auth import TokenAuth
    from flask_merchants.contrib.admin import _get_auth_info

    auth = TokenAuth(token="bearer_token_xyz123", header="Authorization")
    info = _get_auth_info(auth)
    assert info["type"] == "TokenAuth"
    assert info["header"] == "Authorization"
    assert info["masked_value"] == "beare…3"


# ---------------------------------------------------------------------------
# ProvidersView shows enriched info
# ---------------------------------------------------------------------------

def test_providers_view_shows_auth_and_transport(auto_admin_client):
    """ProvidersView renders auth type, transport, and payment count columns."""
    resp = auto_admin_client.get("/admin/merchants_providers/")
    assert resp.status_code == 200
    # No auth for DummyProvider
    assert b"None" in resp.data
    # Transport class name
    assert b"RequestsTransport" in resp.data


def test_providers_view_payment_count(auto_admin_client):
    """ProvidersView shows a non-zero payment count after a checkout."""
    auto_admin_client.post(
        "/merchants/checkout",
        json={"amount": "5.00", "currency": "USD"},
    )
    resp = auto_admin_client.get("/admin/merchants_providers/")
    assert resp.status_code == 200
    # Payment badge should show at least 1
    assert b"badge-primary" in resp.data
