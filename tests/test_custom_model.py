"""Tests for custom model support via PaymentMixin.

Verifies that a developer can bring their own SQLAlchemy model (e.g. Pagos)
and have FlaskMerchants store/retrieve payments through it.
"""

import pytest
from flask import Flask
from flask_admin import Admin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from flask_merchants import FlaskMerchants
from flask_merchants.contrib.sqla import PaymentModelView
from flask_merchants.models import PaymentMixin


# ---------------------------------------------------------------------------
# Fixtures: custom Pagos model backed by in-memory SQLite
# ---------------------------------------------------------------------------

@pytest.fixture
def pagos_app():
    """Flask app where FlaskMerchants uses the custom Pagos model."""

    class Base(DeclarativeBase):
        pass

    db = SQLAlchemy(model_class=Base)

    class Pagos(PaymentMixin, db.Model):
        __tablename__ = "pagos"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)

    application = Flask(__name__)
    application.config["TESTING"] = True
    application.config["SECRET_KEY"] = "test-secret"
    application.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"

    db.init_app(application)

    ext = FlaskMerchants(application, db=db, model=Pagos)

    admin_inst = Admin(application, name="Test Admin")
    admin_inst.add_view(
        PaymentModelView(Pagos, db.session, ext=ext, name="Pagos", endpoint="pagos")
    )

    application.extensions["test_db"] = db
    application.extensions["test_ext"] = ext
    application.extensions["test_model"] = Pagos

    with application.app_context():
        db.create_all()

    return application


@pytest.fixture
def pagos_client(pagos_app):
    return pagos_app.test_client()


@pytest.fixture
def pagos_db(pagos_app):
    return pagos_app.extensions["test_db"]


@pytest.fixture
def pagos_ext(pagos_app):
    return pagos_app.extensions["test_ext"]


@pytest.fixture
def Pagos(pagos_app):
    return pagos_app.extensions["test_model"]


# ---------------------------------------------------------------------------
# PaymentMixin
# ---------------------------------------------------------------------------

def test_payment_mixin_fields(Pagos):
    """Pagos model inherits all required payment columns from PaymentMixin."""
    cols = {c.key for c in Pagos.__table__.columns}
    for field in ("session_id", "redirect_url", "provider", "amount", "currency", "state", "metadata_json"):
        assert field in cols, f"Missing column: {field}"


def test_payment_mixin_to_dict(Pagos):
    """to_dict returns the expected keys."""
    p = Pagos(
        session_id="s1",
        redirect_url="http://example.com",
        provider="dummy",
        amount="10.00",
        currency="USD",
        state="pending",
    )
    d = p.to_dict()
    assert d["session_id"] == "s1"
    assert d["state"] == "pending"
    assert d["currency"] == "USD"


def test_payment_mixin_repr(Pagos):
    """__repr__ uses the subclass name, not 'Payment'."""
    p = Pagos(session_id="s2", state="succeeded")
    assert "Pagos" in repr(p)
    assert "s2" in repr(p)


# ---------------------------------------------------------------------------
# Store helpers with custom model
# ---------------------------------------------------------------------------

def test_save_session_uses_custom_model(pagos_client, pagos_app, pagos_db, Pagos):
    """Checkout stores a row in the custom Pagos table."""
    with pagos_app.app_context():
        resp = pagos_client.post(
            "/merchants/checkout",
            json={"amount": "25.00", "currency": "EUR"},
        )
        assert resp.status_code == 200
        session_id = resp.get_json()["session_id"]

        record = pagos_db.session.query(Pagos).filter_by(session_id=session_id).first()
        assert record is not None
        assert record.state == "pending"
        assert record.amount == "25.00"
        assert record.__class__.__name__ == "Pagos"


def test_get_session_from_custom_model(pagos_client, pagos_app, pagos_ext):
    """get_session retrieves data from the custom model table."""
    with pagos_app.app_context():
        resp = pagos_client.post(
            "/merchants/checkout",
            json={"amount": "5.00", "currency": "USD"},
        )
        session_id = resp.get_json()["session_id"]

        stored = pagos_ext.get_session(session_id)
        assert stored is not None
        assert stored["session_id"] == session_id
        assert stored["amount"] == "5.00"


def test_update_state_on_custom_model(pagos_client, pagos_app, pagos_db, pagos_ext, Pagos):
    """update_state writes to the custom model row."""
    with pagos_app.app_context():
        resp = pagos_client.post(
            "/merchants/checkout",
            json={"amount": "1.00", "currency": "USD"},
        )
        session_id = resp.get_json()["session_id"]

        pagos_ext.update_state(session_id, "succeeded")

        record = pagos_db.session.query(Pagos).filter_by(session_id=session_id).first()
        assert record.state == "succeeded"


def test_all_sessions_from_custom_model(pagos_client, pagos_app, pagos_ext):
    """all_sessions returns rows from the custom model table."""
    with pagos_app.app_context():
        pagos_client.post("/merchants/checkout", json={"amount": "1.00", "currency": "USD"})
        sessions = pagos_ext.all_sessions()
        assert len(sessions) >= 1
        assert all("session_id" in s for s in sessions)


# ---------------------------------------------------------------------------
# Flask-Admin with custom model
# ---------------------------------------------------------------------------

def test_admin_pagos_list(pagos_client, pagos_app):
    """Admin list page renders for the custom model."""
    with pagos_app.app_context():
        resp = pagos_client.get("/admin/pagos/")
        assert resp.status_code == 200


def test_admin_pagos_refund_action(pagos_client, pagos_app, pagos_db, Pagos):
    """Admin refund action marks a Pagos row as refunded."""
    with pagos_app.app_context():
        resp = pagos_client.post("/merchants/checkout", json={"amount": "1.00", "currency": "USD"})
        session_id = resp.get_json()["session_id"]

        record = pagos_db.session.query(Pagos).filter_by(session_id=session_id).first()
        pk = str(record.id)

        action_resp = pagos_client.post(
            "/admin/pagos/action/",
            data={"action": "refund", "rowid": pk},
        )
        assert action_resp.status_code in (200, 302)

        pagos_db.session.expire_all()
        refreshed = pagos_db.session.query(Pagos).filter_by(session_id=session_id).first()
        assert refreshed.state == "refunded"


def test_admin_pagos_sync_action(pagos_client, pagos_app, pagos_db, Pagos):
    """Admin sync action fetches live state from DummyProvider."""
    with pagos_app.app_context():
        resp = pagos_client.post("/merchants/checkout", json={"amount": "1.00", "currency": "USD"})
        session_id = resp.get_json()["session_id"]

        record = pagos_db.session.query(Pagos).filter_by(session_id=session_id).first()
        assert record.state == "pending"
        pk = str(record.id)

        action_resp = pagos_client.post(
            "/admin/pagos/action/",
            data={"action": "sync", "rowid": pk},
        )
        assert action_resp.status_code in (200, 302)

        pagos_db.session.expire_all()
        refreshed = pagos_db.session.query(Pagos).filter_by(session_id=session_id).first()
        # DummyProvider always returns a terminal state
        assert refreshed.state != "pending"
