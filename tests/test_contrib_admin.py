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
# Update state via modal edit
# ---------------------------------------------------------------------------


def test_update_state_success(admin_client, admin_ext):
    """Modal edit view updates the stored state."""
    resp = admin_client.post(
        "/merchants/checkout",
        json={"amount": "10.00", "currency": "USD"},
    )
    session_id = resp.get_json()["session_id"]

    update_resp = admin_client.post(
        f"/admin/payments/edit/?id={session_id}",
        data={"state": "succeeded", "url": "/admin/payments/"},
    )
    # Should redirect back to list
    assert update_resp.status_code == 302

    stored = admin_ext.get_session(session_id)
    assert stored["state"] == "succeeded"


def test_update_state_unknown_id(admin_client):
    """Edit of an unknown payment ID returns to list without crashing."""
    resp = admin_client.post(
        "/admin/payments/edit/?id=does-not-exist",
        data={"state": "failed", "url": "/admin/payments/"},
        follow_redirects=True,
    )
    assert resp.status_code == 200


def test_update_state_modal_get(admin_client, admin_ext):
    """GET to edit endpoint with modal=True returns 200 with a state select field."""
    checkout_resp = admin_client.post(
        "/merchants/checkout",
        json={"amount": "5.00", "currency": "USD"},
    )
    session_id = checkout_resp.get_json()["session_id"]

    resp = admin_client.get(f"/admin/payments/edit/?id={session_id}&modal=True")
    assert resp.status_code == 200
    assert b"state" in resp.data


# ---------------------------------------------------------------------------
# Bulk actions via Flask-Admin action endpoint
# ---------------------------------------------------------------------------


def test_refund_action_success(admin_client, admin_ext):
    """Bulk refund action marks the payment as refunded."""
    resp = admin_client.post(
        "/merchants/checkout",
        json={"amount": "10.00", "currency": "USD"},
    )
    session_id = resp.get_json()["session_id"]

    refund_resp = admin_client.post(
        "/admin/payments/action/",
        data={"action": "refund", "rowid": session_id, "url": "/admin/payments/"},
    )
    assert refund_resp.status_code == 302

    stored = admin_ext.get_session(session_id)
    assert stored["state"] == "refunded"


def test_refund_action_unknown_id(admin_client):
    """Refunding an unknown ID still returns 302 (zero successes, flash message)."""
    resp = admin_client.post(
        "/admin/payments/action/",
        data={"action": "refund", "rowid": "does-not-exist", "url": "/admin/payments/"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"refunded" in resp.data


def test_cancel_action_success(admin_client, admin_ext):
    """Bulk cancel action marks the payment as cancelled."""
    resp = admin_client.post(
        "/merchants/checkout",
        json={"amount": "5.00", "currency": "EUR"},
    )
    session_id = resp.get_json()["session_id"]

    cancel_resp = admin_client.post(
        "/admin/payments/action/",
        data={"action": "cancel", "rowid": session_id, "url": "/admin/payments/"},
    )
    assert cancel_resp.status_code == 302

    stored = admin_ext.get_session(session_id)
    assert stored["state"] == "cancelled"


def test_cancel_action_unknown_id(admin_client):
    """Cancelling an unknown ID still returns 302 (zero successes)."""
    resp = admin_client.post(
        "/admin/payments/action/",
        data={"action": "cancel", "rowid": "does-not-exist", "url": "/admin/payments/"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"cancelled" in resp.data


def test_refund_missing_payment_id(admin_client):
    """Action POST with no rowid returns to list without errors."""
    resp = admin_client.post(
        "/admin/payments/action/",
        data={"action": "refund", "url": "/admin/payments/"},
        follow_redirects=True,
    )
    assert resp.status_code == 200


def test_cancel_missing_payment_id(admin_client):
    """Action POST with no rowid returns to list without errors."""
    resp = admin_client.post(
        "/admin/payments/action/",
        data={"action": "cancel", "url": "/admin/payments/"},
        follow_redirects=True,
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Sync bulk action
# ---------------------------------------------------------------------------


def test_sync_action_success(admin_client, admin_ext):
    """Bulk sync action fetches live state from the provider and updates the store."""
    resp = admin_client.post(
        "/merchants/checkout",
        json={"amount": "1.00", "currency": "USD"},
    )
    session_id = resp.get_json()["session_id"]
    # State starts as pending
    assert admin_ext.get_session(session_id)["state"] == "pending"

    sync_resp = admin_client.post(
        "/admin/payments/action/",
        data={"action": "sync", "rowid": session_id, "url": "/admin/payments/"},
    )
    assert sync_resp.status_code == 302

    # DummyProvider always returns a terminal state; store should be updated
    updated_state = admin_ext.get_session(session_id)["state"]
    assert updated_state != "pending"


def test_sync_action_unknown_id(admin_client):
    """Syncing an unknown ID returns to list with a flash message."""
    resp = admin_client.post(
        "/admin/payments/action/",
        data={"action": "sync", "rowid": "does-not-exist", "url": "/admin/payments/"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"synced" in resp.data


def test_sync_missing_payment_id(admin_client):
    """Sync action with no rowid returns to list without errors."""
    resp = admin_client.post(
        "/admin/payments/action/",
        data={"action": "sync", "url": "/admin/payments/"},
        follow_redirects=True,
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# PaymentView class
# ---------------------------------------------------------------------------


def test_payment_view_is_base_view():
    """PaymentView is a subclass of Flask-Admin BaseView (via BaseModelView)."""
    from flask_admin import BaseView

    assert issubclass(PaymentView, BaseView)


def test_payment_view_is_model_view():
    """PaymentView is a subclass of Flask-Admin BaseModelView."""
    from flask_admin.model import BaseModelView

    assert issubclass(PaymentView, BaseModelView)


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
    """ProvidersView is a subclass of Flask-Admin BaseView (via BaseModelView)."""
    from flask_admin import BaseView

    from flask_merchants.contrib.admin import ProvidersView

    assert issubclass(ProvidersView, BaseView)


def test_providers_view_is_model_view():
    """ProvidersView is a subclass of Flask-Admin BaseModelView."""
    from flask_admin.model import BaseModelView

    from flask_merchants.contrib.admin import ProvidersView

    assert issubclass(ProvidersView, BaseModelView)


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


def test_providers_view_shows_provider_info(auto_admin_client):
    """ProvidersView renders ProviderInfo fields from merchants.describe_providers()."""
    resp = auto_admin_client.get("/admin/merchants_providers/")
    assert resp.status_code == 200
    # DummyProvider's name field from ProviderInfo
    assert b"Dummy" in resp.data


def test_providers_view_shows_version(auto_admin_client):
    """ProvidersView shows the provider version from ProviderInfo."""
    import merchants

    # Get actual version from describe_providers to avoid hardcoding
    infos = merchants.describe_providers()
    dummy_info = next((p for p in infos if p.key == "dummy"), None)
    assert dummy_info is not None

    resp = auto_admin_client.get("/admin/merchants_providers/")
    assert resp.status_code == 200
    assert dummy_info.version.encode() in resp.data


def test_providers_view_shows_base_url_and_transport(auto_admin_client):
    """ProvidersView renders base_url and transport columns."""
    resp = auto_admin_client.get("/admin/merchants_providers/")
    assert resp.status_code == 200
    assert b"RequestsTransport" in resp.data


def test_providers_view_shows_auth_type_with_tooltip(auto_admin_client):
    """ProvidersView renders auth_type as a badge with a tooltip for auth_header/auth_masked_value."""
    resp = auto_admin_client.get("/admin/merchants_providers/")
    assert resp.status_code == 200
    assert b'data-toggle="tooltip"' in resp.data


def test_providers_view_payment_count(auto_admin_client):
    """ProvidersView shows a non-zero payment count badge after a checkout."""
    auto_admin_client.post(
        "/merchants/checkout",
        json={"amount": "5.00", "currency": "USD"},
    )
    resp = auto_admin_client.get("/admin/merchants_providers/")
    assert resp.status_code == 200
    assert b"badge-primary" in resp.data


# ---------------------------------------------------------------------------
# Template structure
# ---------------------------------------------------------------------------


def test_payments_list_uses_model_list_table(admin_client):
    """PaymentView list page renders the standard Flask-Admin model-list table."""
    resp = admin_client.get("/admin/payments/")
    assert resp.status_code == 200
    assert b"model-list" in resp.data
    assert b"table-hover" in resp.data


def test_payments_list_has_nav_tabs(admin_client):
    """PaymentView list page includes the nav-tabs header bar."""
    resp = admin_client.get("/admin/payments/")
    assert resp.status_code == 200
    assert b"nav-tabs" in resp.data


def test_payments_list_color_coded_badges(admin_client, admin_ext):
    """Color-coded state badges are rendered for known states."""
    admin_client.post("/merchants/checkout", json={"amount": "1.00", "currency": "USD"})
    resp = admin_client.get("/admin/payments/")
    assert resp.status_code == 200
    # Pending state should show a secondary badge by default
    assert b"badge-secondary" in resp.data


def test_payments_list_actions_in_first_column(admin_client, admin_ext):
    """Row edit action and bulk action dropdown appear in the list."""
    admin_client.post("/merchants/checkout", json={"amount": "1.00", "currency": "USD"})
    resp = admin_client.get("/admin/payments/")
    assert resp.status_code == 200
    # Bulk action dropdown
    assert b"With selected" in resp.data
    # Row edit popup icon
    assert b"fa-pencil" in resp.data or b"edit" in resp.data


def test_providers_list_uses_model_list_table(auto_admin_client):
    """ProvidersView list page renders the standard Flask-Admin model-list table."""
    resp = auto_admin_client.get("/admin/merchants_providers/")
    assert resp.status_code == 200
    assert b"model-list" in resp.data
    assert b"table-hover" in resp.data


def test_providers_list_has_nav_tabs(auto_admin_client):
    """ProvidersView list page includes the nav-tabs header bar."""
    resp = auto_admin_client.get("/admin/merchants_providers/")
    assert resp.status_code == 200
    assert b"nav-tabs" in resp.data


# ---------------------------------------------------------------------------
# Configurable menu item names via app config
# ---------------------------------------------------------------------------


def test_configurable_payment_view_name_via_config():
    """MERCHANTS_PAYMENT_VIEW_NAME config overrides the Payments menu label."""
    from flask_admin import Admin

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "s"
    app.config["MERCHANTS_PAYMENT_VIEW_NAME"] = "Pagos"

    admin = Admin(app, name="Test")
    FlaskMerchants(app, admin=admin)

    with app.test_client() as client:
        resp = client.get("/admin/merchants_payments/")
        assert resp.status_code == 200
        assert b"Pagos" in resp.data


def test_configurable_provider_view_name_via_config():
    """MERCHANTS_PROVIDER_VIEW_NAME config overrides the Providers menu label."""
    from flask_admin import Admin

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "s"
    app.config["MERCHANTS_PROVIDER_VIEW_NAME"] = "Proveedores"

    admin = Admin(app, name="Test")
    FlaskMerchants(app, admin=admin)

    with app.test_client() as client:
        resp = client.get("/admin/merchants_providers/")
        assert resp.status_code == 200
        assert b"Proveedores" in resp.data


def test_register_admin_views_custom_names():
    """register_admin_views accepts payment_name and provider_name parameters."""
    from flask_admin import Admin

    from flask_merchants.contrib.admin import register_admin_views

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "s"
    admin = Admin(app, name="Test")
    ext = FlaskMerchants(app)
    register_admin_views(admin, ext, payment_name="Paiements", provider_name="Fournisseurs")

    with app.test_client() as client:
        resp = client.get("/admin/merchants_payments/")
        assert resp.status_code == 200
        assert b"Paiements" in resp.data

        resp = client.get("/admin/merchants_providers/")
        assert resp.status_code == 200
        assert b"Fournisseurs" in resp.data


def test_default_config_values_set_on_init_app():
    """init_app sets MERCHANTS_PAYMENT_VIEW_NAME and MERCHANTS_PROVIDER_VIEW_NAME defaults."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "s"
    FlaskMerchants(app)

    assert app.config["MERCHANTS_PAYMENT_VIEW_NAME"] == "Payments"
    assert app.config["MERCHANTS_PROVIDER_VIEW_NAME"] == "Providers"


# ---------------------------------------------------------------------------
# ModelView search and sort features
# ---------------------------------------------------------------------------


def test_payment_view_search_supported(admin_client, admin_ext):
    """PaymentView list page includes a search bar (search_supported=True)."""
    resp = admin_client.get("/admin/payments/")
    assert resp.status_code == 200
    # Flask-Admin renders a search input when search is supported
    assert b"search" in resp.data.lower()


def test_payment_view_search_filters_results(admin_client, admin_ext):
    """Search query filters displayed payments by session_id, provider, or state."""
    admin_client.post("/merchants/checkout", json={"amount": "1.00", "currency": "USD"})

    resp = admin_client.get("/admin/payments/?search=dummy_sess_")
    assert resp.status_code == 200
    assert b"dummy_sess_" in resp.data

    resp = admin_client.get("/admin/payments/?search=no_match_xyz")
    assert resp.status_code == 200
    assert b"dummy_sess_" not in resp.data


def test_payment_view_sort_column_links(admin_client):
    """PaymentView renders sortable column header links."""
    resp = admin_client.get("/admin/payments/")
    assert resp.status_code == 200
    # Sortable columns should produce links with sort param
    assert b"?sort=" in resp.data


def test_payment_view_sort_by_state(admin_client, admin_ext):
    """Payments can be sorted by state via the sort URL param."""
    # Create two checkouts and give them different states
    r1 = admin_client.post("/merchants/checkout", json={"amount": "1.00", "currency": "USD"})
    r2 = admin_client.post("/merchants/checkout", json={"amount": "2.00", "currency": "USD"})
    sid1 = r1.get_json()["session_id"]
    sid2 = r2.get_json()["session_id"]
    admin_ext.update_state(sid1, "succeeded")
    admin_ext.update_state(sid2, "failed")

    # Sort by state column (index 4 in column_list)
    resp = admin_client.get("/admin/payments/?sort=4")
    assert resp.status_code == 200
    assert b"succeeded" in resp.data or b"failed" in resp.data


def test_providers_view_search_supported(auto_admin_client):
    """ProvidersView list page includes a search bar."""
    resp = auto_admin_client.get("/admin/merchants_providers/")
    assert resp.status_code == 200
    assert b"search" in resp.data.lower()


def test_providers_view_sort_column_links(auto_admin_client):
    """ProvidersView renders sortable column header links."""
    resp = auto_admin_client.get("/admin/merchants_providers/")
    assert resp.status_code == 200
    assert b"?sort=" in resp.data


def test_payment_view_column_config():
    """PaymentView exposes column_searchable_list and column_sortable_list."""
    assert "session_id" in PaymentView.column_searchable_list
    assert "provider" in PaymentView.column_searchable_list
    assert "state" in PaymentView.column_searchable_list
    assert "provider" in PaymentView.column_sortable_list
    assert "state" in PaymentView.column_sortable_list


def test_providers_view_column_config():
    """ProvidersView exposes correct column_list, column_searchable_list, and column_sortable_list."""
    from flask_merchants.contrib.admin import ProvidersView

    assert "key" in ProvidersView.column_searchable_list
    assert "name" in ProvidersView.column_searchable_list
    assert "key" in ProvidersView.column_sortable_list
    assert "name" in ProvidersView.column_sortable_list
    assert "version" in ProvidersView.column_sortable_list
    assert "payment_count" in ProvidersView.column_sortable_list
    # These columns should appear in the list view
    for col in ("key", "name", "version", "base_url", "auth_type", "transport", "payment_count"):
        assert col in ProvidersView.column_list
    # auth_header and auth_masked_value should be in details only, not the list
    assert "auth_header" not in ProvidersView.column_list
    assert "auth_masked_value" not in ProvidersView.column_list
    assert "auth_header" in ProvidersView.column_details_list
    assert "auth_masked_value" in ProvidersView.column_details_list


# ---------------------------------------------------------------------------
# ProvidersView can_view_details and details endpoint
# ---------------------------------------------------------------------------


def test_providers_view_can_view_details_is_true():
    """ProvidersView has can_view_details set to True."""
    from flask_merchants.contrib.admin import ProvidersView

    assert ProvidersView.can_view_details is True


def test_providers_view_can_create_edit_delete_are_false():
    """ProvidersView has can_create, can_edit, can_delete all set to False."""
    from flask_merchants.contrib.admin import ProvidersView

    assert ProvidersView.can_create is False
    assert ProvidersView.can_edit is False
    assert ProvidersView.can_delete is False


def test_providers_view_details_page(auto_admin_client):
    """ProvidersView details page is accessible for the dummy provider."""
    resp = auto_admin_client.get("/admin/merchants_providers/details/?id=dummy")
    assert resp.status_code == 200
    assert b"dummy" in resp.data


def test_providers_view_uses_describe_providers(auto_admin_client):
    """ProvidersView list shows all ProviderInfo fields from merchants.describe_providers()."""
    import merchants

    infos = merchants.describe_providers()
    resp = auto_admin_client.get("/admin/merchants_providers/")
    assert resp.status_code == 200
    # Every registered provider key should appear in the list
    for info in infos:
        assert info.key.encode() in resp.data
