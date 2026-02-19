"""Shared pytest fixtures for flask-merchants tests."""

import pytest
from flask import Flask

from flask_merchants import Merchants


@pytest.fixture
def app():
    """Flask app configured with DummyProvider and test settings."""
    application = Flask(__name__)
    application.config["TESTING"] = True
    application.config["SECRET_KEY"] = "test-secret"
    application.config["MERCHANTS_WEBHOOK_SECRET"] = None

    ext = Merchants(application)
    application.extensions["merchants_ext"] = ext

    yield application


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def ext(app):
    """The Merchants extension instance."""
    return app.extensions["merchants"]
