"""Tests for the FlaskMerchants Flask extension initialisation."""

import merchants as sdk
import pytest
from flask import Flask

from flask_merchants import FlaskMerchants
from flask_merchants.version import __version__


def test_version_string():
    """__version__ is a non-empty string."""
    assert isinstance(__version__, str)
    assert __version__


def test_init_direct():
    """Extension initialised directly with app."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    ext = FlaskMerchants(app)

    assert "merchants" in app.extensions
    assert app.extensions["merchants"] is ext


def test_init_app_factory():
    """Extension uses the application-factory pattern."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    ext = FlaskMerchants()
    ext.init_app(app)

    assert "merchants" in app.extensions
    assert app.extensions["merchants"] is ext


def test_init_app_factory_with_provider():
    """init_app accepts provider= and wires it as the default client."""
    from merchants.providers.dummy import DummyProvider

    app = Flask(__name__)
    app.config["TESTING"] = True
    provider = DummyProvider(always_state=sdk.PaymentState.FAILED)

    ext = FlaskMerchants()
    ext.init_app(app, provider=provider)

    assert ext.client._provider is provider


def test_init_app_factory_with_providers():
    """init_app accepts providers= and registers all of them."""
    import merchants.providers as _mp
    from merchants.providers.dummy import DummyProvider

    class AltProvider(DummyProvider):
        key = "alt_init_app"

    saved = dict(_mp._REGISTRY)
    try:
        app = Flask(__name__)
        app.config["TESTING"] = True
        ext = FlaskMerchants()
        ext.init_app(app, providers=[DummyProvider(), AltProvider()])

        assert "dummy" in ext.list_providers()
        assert "alt_init_app" in ext.list_providers()
    finally:
        _mp._REGISTRY.clear()
        _mp._REGISTRY.update(saved)


def test_init_app_factory_with_db():
    """init_app accepts db= and persists payments to the database."""
    from flask_sqlalchemy import SQLAlchemy

    from flask_merchants.models import Base, Payment

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"

    db = SQLAlchemy(model_class=Base)
    db.init_app(app)

    ext = FlaskMerchants()
    ext.init_app(app, db=db)

    with app.app_context():
        db.create_all()
        with app.test_client() as tc:
            resp = tc.post("/merchants/checkout", json={"amount": "5.00", "currency": "USD"})
            session_id = resp.get_json()["session_id"]
        record = db.session.query(Payment).filter_by(session_id=session_id).first()
        assert record is not None
        assert record.state == "pending"


def test_init_app_factory_with_models():
    """init_app accepts models= and uses the custom model class."""
    from flask_sqlalchemy import SQLAlchemy
    from sqlalchemy import Integer
    from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

    from flask_merchants.models import PaymentMixin

    class MyBase(DeclarativeBase):
        pass

    db = SQLAlchemy(model_class=MyBase)

    class Pagos(PaymentMixin, db.Model):
        __tablename__ = "pagos_init_app"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    db.init_app(app)

    ext = FlaskMerchants()
    ext.init_app(app, db=db, models=[Pagos])

    assert ext._get_model_classes() == [Pagos]


def test_init_app_overrides_constructor_values():
    """init_app keyword args override values set in __init__."""
    from merchants.providers.dummy import DummyProvider

    app = Flask(__name__)
    app.config["TESTING"] = True

    # Set a provider in __init__, then override it in init_app
    old_provider = DummyProvider()
    new_provider = DummyProvider(always_state=sdk.PaymentState.SUCCEEDED)

    ext = FlaskMerchants(provider=old_provider)
    ext.init_app(app, provider=new_provider)

    assert ext.client._provider is new_provider


def test_constructor_and_init_app_both_work():
    """Both FlaskMerchants(app, db=db) and ext.init_app(app, db=db) are equivalent."""
    from flask_sqlalchemy import SQLAlchemy

    from flask_merchants.models import Base

    # Style 1: everything in constructor
    app1 = Flask(__name__)
    app1.config["TESTING"] = True
    app1.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    db1 = SQLAlchemy(model_class=Base)
    db1.init_app(app1)
    ext1 = FlaskMerchants(app1, db=db1)

    # Style 2: config deferred to init_app
    app2 = Flask(__name__)
    app2.config["TESTING"] = True
    app2.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    db2 = SQLAlchemy(model_class=Base)
    db2.init_app(app2)
    ext2 = FlaskMerchants()
    ext2.init_app(app2, db=db2)

    assert ext1._db is db1
    assert ext2._db is db2
    # Both have a working client
    assert isinstance(ext1.client, sdk.Client)
    assert isinstance(ext2.client, sdk.Client)


def test_client_property(ext):
    """ext.client returns a merchants.Client instance."""
    assert isinstance(ext.client, sdk.Client)


def test_client_before_init_raises():
    """Accessing client before init_app raises RuntimeError."""
    ext = FlaskMerchants()
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
    FlaskMerchants(app)

    rules = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/pay/checkout" in rules


def test_custom_provider():
    """Extension accepts a custom provider instance."""
    from merchants.providers.dummy import DummyProvider

    app = Flask(__name__)
    app.config["TESTING"] = True
    provider = DummyProvider(always_state=sdk.PaymentState.FAILED)
    ext = FlaskMerchants(app, provider=provider)

    assert ext.client._provider is provider
