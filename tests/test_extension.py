"""Tests for the Merchants Flask extension initialisation."""

import pytest
from flask import Flask

import merchants as sdk
from flask_merchants import Merchants


def test_init_direct():
    """Extension initialised directly with app."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    ext = Merchants(app)

    assert "merchants" in app.extensions
    assert app.extensions["merchants"] is ext


def test_init_app_factory():
    """Extension uses the application-factory pattern."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    ext = Merchants()
    ext.init_app(app)

    assert "merchants" in app.extensions
    assert app.extensions["merchants"] is ext


def test_client_property(ext):
    """ext.client returns a merchants.Client instance."""
    assert isinstance(ext.client, sdk.Client)


def test_client_before_init_raises():
    """Accessing client before init_app raises RuntimeError."""
    ext = Merchants()
    with pytest.raises(RuntimeError, match="not initialised"):
        _ = ext.client


def test_default_url_prefix(app):
    """Blueprint is registered under the default /merchants prefix."""
    rules = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/merchants/checkout" in rules
    assert "/merchants/webhook" in rules
    assert "/merchants/success" in rules
    assert "/merchants/cancel" in rules


def test_custom_url_prefix():
    """Blueprint is registered under a custom URL prefix."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["MERCHANTS_URL_PREFIX"] = "/pay"
    Merchants(app)

    rules = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/pay/checkout" in rules


def test_custom_provider():
    """Extension accepts a custom provider instance."""
    from merchants.providers.dummy import DummyProvider

    app = Flask(__name__)
    app.config["TESTING"] = True
    provider = DummyProvider(always_state=sdk.PaymentState.FAILED)
    ext = Merchants(app, provider=provider)

    assert ext.client._provider is provider
