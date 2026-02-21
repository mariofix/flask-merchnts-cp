"""Tests for multiple-model support in a single FlaskMerchants instance.

Verifies that one ext instance can manage two models (Pagos + Paiements):
- save_session routes to a specific model via model_class=
- get_session searches all models
- update_state searches all models
- all_sessions combines all models; model_class= filters to one
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
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def multi_app():
    """Flask app with a single FlaskMerchants and two payment models."""

    class Base(DeclarativeBase):
        pass

    db = SQLAlchemy(model_class=Base)

    class Pagos(PaymentMixin, db.Model):
        __tablename__ = "pagos"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)

    class Paiements(PaymentMixin, db.Model):
        __tablename__ = "paiements"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)

    application = Flask(__name__)
    application.config["TESTING"] = True
    application.config["SECRET_KEY"] = "test-secret"
    application.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"

    db.init_app(application)

    ext = FlaskMerchants(application, db=db, models=[Pagos, Paiements])

    admin_inst = Admin(application, name="Test Admin")
    admin_inst.add_view(
        PaymentModelView(Pagos, db.session, ext=ext, name="Pagos", endpoint="pagos")
    )
    admin_inst.add_view(
        PaymentModelView(Paiements, db.session, ext=ext, name="Paiements", endpoint="paiements")
    )

    application.extensions["test_db"] = db
    application.extensions["test_ext"] = ext
    application.extensions["Pagos"] = Pagos
    application.extensions["Paiements"] = Paiements

    with application.app_context():
        db.create_all()

    return application


@pytest.fixture
def multi_client(multi_app):
    return multi_app.test_client()


@pytest.fixture
def multi_db(multi_app):
    return multi_app.extensions["test_db"]


@pytest.fixture
def multi_ext(multi_app):
    return multi_app.extensions["test_ext"]


@pytest.fixture
def Pagos(multi_app):
    return multi_app.extensions["Pagos"]


@pytest.fixture
def Paiements(multi_app):
    return multi_app.extensions["Paiements"]


# ---------------------------------------------------------------------------
# _get_model_classes / _payment_model
# ---------------------------------------------------------------------------


def test_get_model_classes_returns_both(multi_ext, Pagos, Paiements):
    """_get_model_classes returns all registered models."""
    classes = multi_ext._get_model_classes()
    assert Pagos in classes
    assert Paiements in classes
    assert len(classes) == 2


def test_payment_model_is_first(multi_ext, Pagos):
    """_payment_model returns the first registered model."""
    assert multi_ext._payment_model is Pagos


# ---------------------------------------------------------------------------
# models= vs model= construction
# ---------------------------------------------------------------------------


def test_models_list_construction():
    """FlaskMerchants(models=[...]) populates _models correctly."""
    app = Flask(__name__)
    app.config["TESTING"] = True

    class Base(DeclarativeBase):
        pass

    db = SQLAlchemy(model_class=Base)

    class A(PaymentMixin, db.Model):
        __tablename__ = "a"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)

    class B(PaymentMixin, db.Model):
        __tablename__ = "b"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)

    ext = FlaskMerchants(models=[A, B])
    assert ext._get_model_classes() == [A, B]


def test_single_model_still_works():
    """model= (single) backward compat: _get_model_classes returns [model]."""

    class Base(DeclarativeBase):
        pass

    db = SQLAlchemy(model_class=Base)

    class C(PaymentMixin, db.Model):
        __tablename__ = "c"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)

    ext = FlaskMerchants(model=C)
    assert ext._get_model_classes() == [C]
    assert ext._payment_model is C


# ---------------------------------------------------------------------------
# save_session with explicit model_class
# ---------------------------------------------------------------------------


def test_save_session_to_pagos(multi_client, multi_app, multi_db, multi_ext, Pagos, Paiements):
    """save_session with model_class=Pagos saves only to Pagos table."""
    with multi_app.app_context():
        # Create checkout (blueprint auto-saves to first model = Pagos)
        resp = multi_client.post(
            "/merchants/checkout",
            json={"amount": "10.00", "currency": "EUR"},
        )
        session_id = resp.get_json()["session_id"]

        pagos_record = multi_db.session.query(Pagos).filter_by(session_id=session_id).first()
        paiements_record = (
            multi_db.session.query(Paiements).filter_by(session_id=session_id).first()
        )

        assert pagos_record is not None, "Expected record in Pagos table"
        assert paiements_record is None, "Should NOT be in Paiements table"


def test_save_session_explicit_paiements(multi_app, multi_db, multi_ext, Pagos, Paiements):
    """save_session(model_class=Paiements) saves to Paiements table only."""
    with multi_app.app_context():
        session = multi_ext.client.payments.create_checkout(
            amount="20.00",
            currency="EUR",
            success_url="http://localhost/success",
            cancel_url="http://localhost/cancel",
        )
        multi_ext.save_session(session, model_class=Paiements)

        pagos_record = (
            multi_db.session.query(Pagos).filter_by(session_id=session.session_id).first()
        )
        paiements_record = (
            multi_db.session.query(Paiements).filter_by(session_id=session.session_id).first()
        )

        assert paiements_record is not None, "Expected record in Paiements table"
        assert pagos_record is None, "Should NOT be in Pagos table"


# ---------------------------------------------------------------------------
# get_session searches all models
# ---------------------------------------------------------------------------


def test_get_session_finds_pagos_record(multi_app, multi_db, multi_ext, Pagos):
    """get_session returns a record stored in the Pagos table."""
    with multi_app.app_context():
        session = multi_ext.client.payments.create_checkout(
            amount="5.00",
            currency="USD",
            success_url="http://localhost/s",
            cancel_url="http://localhost/c",
        )
        multi_ext.save_session(session, model_class=Pagos)

        stored = multi_ext.get_session(session.session_id)
        assert stored is not None
        assert stored["session_id"] == session.session_id


def test_get_session_finds_paiements_record(multi_app, multi_db, multi_ext, Paiements):
    """get_session returns a record stored in the Paiements table."""
    with multi_app.app_context():
        session = multi_ext.client.payments.create_checkout(
            amount="15.00",
            currency="EUR",
            success_url="http://localhost/s",
            cancel_url="http://localhost/c",
        )
        multi_ext.save_session(session, model_class=Paiements)

        stored = multi_ext.get_session(session.session_id)
        assert stored is not None
        assert stored["session_id"] == session.session_id


# ---------------------------------------------------------------------------
# update_state searches all models
# ---------------------------------------------------------------------------


def test_update_state_on_paiements(multi_app, multi_db, multi_ext, Paiements):
    """update_state finds and updates a record in the Paiements table."""
    with multi_app.app_context():
        session = multi_ext.client.payments.create_checkout(
            amount="30.00",
            currency="EUR",
            success_url="http://localhost/s",
            cancel_url="http://localhost/c",
        )
        multi_ext.save_session(session, model_class=Paiements)

        result = multi_ext.update_state(session.session_id, "succeeded")
        assert result is True

        record = multi_db.session.query(Paiements).filter_by(session_id=session.session_id).first()
        assert record.state == "succeeded"


# ---------------------------------------------------------------------------
# all_sessions
# ---------------------------------------------------------------------------


def test_all_sessions_combines_both_models(multi_app, multi_ext, Pagos, Paiements):
    """all_sessions() without filter returns records from all models."""
    with multi_app.app_context():
        s1 = multi_ext.client.payments.create_checkout(
            amount="1.00",
            currency="USD",
            success_url="http://localhost/s",
            cancel_url="http://localhost/c",
        )
        s2 = multi_ext.client.payments.create_checkout(
            amount="2.00",
            currency="EUR",
            success_url="http://localhost/s",
            cancel_url="http://localhost/c",
        )
        multi_ext.save_session(s1, model_class=Pagos)
        multi_ext.save_session(s2, model_class=Paiements)

        all_sess = multi_ext.all_sessions()
        ids = {s["session_id"] for s in all_sess}
        assert s1.session_id in ids
        assert s2.session_id in ids


def test_all_sessions_filtered_by_model(multi_app, multi_ext, Pagos, Paiements):
    """all_sessions(model_class=X) returns only records from that model."""
    with multi_app.app_context():
        s1 = multi_ext.client.payments.create_checkout(
            amount="1.00",
            currency="USD",
            success_url="http://localhost/s",
            cancel_url="http://localhost/c",
        )
        s2 = multi_ext.client.payments.create_checkout(
            amount="2.00",
            currency="EUR",
            success_url="http://localhost/s",
            cancel_url="http://localhost/c",
        )
        multi_ext.save_session(s1, model_class=Pagos)
        multi_ext.save_session(s2, model_class=Paiements)

        pagos_sess = multi_ext.all_sessions(model_class=Pagos)
        paiements_sess = multi_ext.all_sessions(model_class=Paiements)

        pagos_ids = {s["session_id"] for s in pagos_sess}
        paiements_ids = {s["session_id"] for s in paiements_sess}

        assert s1.session_id in pagos_ids
        assert s1.session_id not in paiements_ids
        assert s2.session_id in paiements_ids
        assert s2.session_id not in pagos_ids


# ---------------------------------------------------------------------------
# Flask-Admin with multi-model ext
# ---------------------------------------------------------------------------


def test_admin_pagos_view_renders(multi_client, multi_app):
    with multi_app.app_context():
        resp = multi_client.get("/admin/pagos/")
        assert resp.status_code == 200


def test_admin_paiements_view_renders(multi_client, multi_app):
    with multi_app.app_context():
        resp = multi_client.get("/admin/paiements/")
        assert resp.status_code == 200


def test_admin_refund_paiements(multi_client, multi_app, multi_db, multi_ext, Paiements):
    """Admin refund action works on Paiements rows via the shared ext."""
    with multi_app.app_context():
        session = multi_ext.client.payments.create_checkout(
            amount="5.00",
            currency="EUR",
            success_url="http://localhost/s",
            cancel_url="http://localhost/c",
        )
        multi_ext.save_session(session, model_class=Paiements)

        record = multi_db.session.query(Paiements).filter_by(session_id=session.session_id).first()
        pk = str(record.id)

        resp = multi_client.post(
            "/admin/paiements/action/",
            data={"action": "refund", "rowid": pk},
        )
        assert resp.status_code in (200, 302)

        multi_db.session.expire_all()
        refreshed = (
            multi_db.session.query(Paiements).filter_by(session_id=session.session_id).first()
        )
        assert refreshed.state == "refunded"
