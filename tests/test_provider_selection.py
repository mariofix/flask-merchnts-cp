"""Tests for payment provider selection feature."""

import merchants
import pytest
from flask import Flask
from merchants.providers.dummy import DummyProvider

from flask_merchants import FlaskMerchants

# ---------------------------------------------------------------------------
# Registry isolation
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_merchants_registry():
    """Save and restore the merchants provider registry around each test."""
    import merchants.providers as _mp

    saved = dict(_mp._REGISTRY)
    yield
    _mp._REGISTRY.clear()
    _mp._REGISTRY.update(saved)


# ---------------------------------------------------------------------------
# Second DummyProvider subclass with a distinct key
# ---------------------------------------------------------------------------


class AltDummyProvider(DummyProvider):
    key = "alt_dummy"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def multi_provider_app():
    """Flask app with two providers registered via the merchants registry."""
    merchants.register_provider(DummyProvider())
    merchants.register_provider(AltDummyProvider())

    application = Flask(__name__)
    application.config["TESTING"] = True
    application.config["SECRET_KEY"] = "test-secret"

    ext = FlaskMerchants(application)
    application.extensions["merchants_ext"] = ext
    yield application


@pytest.fixture
def multi_client(multi_provider_app):
    return multi_provider_app.test_client()


@pytest.fixture
def multi_ext(multi_provider_app):
    return multi_provider_app.extensions["merchants"]


# ---------------------------------------------------------------------------
# list_providers / get_client
# ---------------------------------------------------------------------------


def test_list_providers_single(app):
    """Default (single DummyProvider) app lists one provider."""
    ext = app.extensions["merchants"]
    providers = ext.list_providers()
    assert "dummy" in providers


def test_list_providers_multi(multi_ext):
    """Multi-provider app lists all registered provider keys."""
    providers = multi_ext.list_providers()
    assert "dummy" in providers
    assert "alt_dummy" in providers


def test_list_providers_reflects_live_registry():
    """list_providers() reflects providers registered after init_app."""
    application = Flask(__name__)
    application.config["TESTING"] = True
    ext = FlaskMerchants(application)

    # Register a new provider after init
    merchants.register_provider(AltDummyProvider())
    assert "alt_dummy" in ext.list_providers()


def test_get_client_default(app):
    """get_client(None) returns the default client."""
    ext = app.extensions["merchants"]
    assert ext.get_client() is ext.client


def test_get_client_by_key(multi_ext):
    """get_client with a valid key returns the correct client."""
    client_a = multi_ext.get_client("dummy")
    client_b = multi_ext.get_client("alt_dummy")
    assert client_a is not client_b


def test_get_client_by_key_cached(multi_ext):
    """get_client returns the same cached client on repeated calls."""
    assert multi_ext.get_client("alt_dummy") is multi_ext.get_client("alt_dummy")


def test_get_client_unknown_key(multi_ext):
    """get_client with an unknown key raises KeyError."""
    with pytest.raises(KeyError, match="Unknown provider"):
        multi_ext.get_client("nonexistent")


# ---------------------------------------------------------------------------
# /providers endpoint
# ---------------------------------------------------------------------------


def test_providers_endpoint_single(client):
    """GET /merchants/providers returns at least 'dummy'."""
    resp = client.get("/merchants/providers")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "providers" in data
    assert "dummy" in data["providers"]


def test_providers_endpoint_multi(multi_client):
    """GET /merchants/providers lists all registered providers."""
    resp = multi_client.get("/merchants/providers")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "dummy" in data["providers"]
    assert "alt_dummy" in data["providers"]


# ---------------------------------------------------------------------------
# /checkout with provider selection
# ---------------------------------------------------------------------------


def test_checkout_default_provider(client, ext):
    """Checkout without provider field uses the default provider."""
    resp = client.post("/merchants/checkout", json={"amount": "5.00", "currency": "USD"})
    assert resp.status_code == 200
    session_id = resp.get_json()["session_id"]
    stored = ext.get_session(session_id)
    assert stored["provider"] == "dummy"


def test_checkout_explicit_provider(multi_client, multi_ext):
    """Checkout with explicit provider field uses that provider."""
    resp = multi_client.post(
        "/merchants/checkout",
        json={"amount": "5.00", "currency": "USD", "provider": "alt_dummy"},
    )
    assert resp.status_code == 200
    session_id = resp.get_json()["session_id"]
    stored = multi_ext.get_session(session_id)
    assert stored["provider"] == "alt_dummy"


def test_checkout_unknown_provider_returns_400(multi_client):
    """Checkout with an unknown provider key returns HTTP 400."""
    resp = multi_client.post(
        "/merchants/checkout",
        json={"amount": "5.00", "currency": "USD", "provider": "nonexistent"},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data
    assert "nonexistent" in data["error"]


def test_checkout_provider_stored_in_request_payload(multi_client, multi_ext):
    """The selected provider key is stored in request_payload."""
    resp = multi_client.post(
        "/merchants/checkout",
        json={"amount": "3.00", "currency": "EUR", "provider": "alt_dummy"},
    )
    session_id = resp.get_json()["session_id"]
    stored = multi_ext.get_session(session_id)
    assert stored["request_payload"]["provider"] == "alt_dummy"


def test_checkout_provider_registered_after_init(app, ext):
    """A provider registered after init_app is usable in checkout."""
    merchants.register_provider(AltDummyProvider())
    with app.test_client() as tc:
        resp = tc.post(
            "/merchants/checkout",
            json={"amount": "1.00", "currency": "USD", "provider": "alt_dummy"},
        )
    assert resp.status_code == 200
    session_id = resp.get_json()["session_id"]
    stored = ext.get_session(session_id)
    assert stored["provider"] == "alt_dummy"
