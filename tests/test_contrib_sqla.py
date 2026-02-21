"""Tests for flask_merchants.contrib.sqla (Flask-Admin SQLAlchemy ModelView)."""

from decimal import Decimal

import pytest
from flask import Flask
from flask_admin import Admin
from flask_sqlalchemy import SQLAlchemy

from flask_merchants import FlaskMerchants
from flask_merchants.contrib.sqla import PaymentModelView
from flask_merchants.models import Base, Payment


@pytest.fixture
def sqla_app():
    """Flask app with in-memory SQLite, FlaskMerchants and PaymentModelView."""
    application = Flask(__name__)
    application.config["TESTING"] = True
    application.config["SECRET_KEY"] = "test-secret"
    application.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"

    db = SQLAlchemy(model_class=Base)
    db.init_app(application)

    ext = FlaskMerchants(application, db=db)

    admin_inst = Admin(application, name="Test Admin")
    admin_inst.add_view(
        PaymentModelView(Payment, db.session, ext=ext, name="Payments", endpoint="payments")
    )

    application.extensions["test_db"] = db
    application.extensions["test_ext"] = ext

    with application.app_context():
        db.create_all()

    return application


@pytest.fixture
def sqla_client(sqla_app):
    return sqla_app.test_client()


@pytest.fixture
def sqla_db(sqla_app):
    return sqla_app.extensions["test_db"]


@pytest.fixture
def sqla_ext(sqla_app):
    return sqla_app.extensions["test_ext"]


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


def test_payment_model_fields():
    """Payment model has the expected columns."""
    cols = {c.key for c in Payment.__table__.columns}
    assert "session_id" in cols
    assert "state" in cols
    assert "provider" in cols
    assert "amount" in cols
    assert "currency" in cols
    assert "request_payload" in cols
    assert "response_payload" in cols


def test_payment_model_repr():
    p = Payment(
        session_id="s1",
        state="pending",
        redirect_url="http://x",
        provider="dummy",
        amount="1.00",
        currency="USD",
    )
    assert "s1" in repr(p)
    assert "pending" in repr(p)


def test_payment_to_dict():
    p = Payment(
        session_id="s2",
        redirect_url="http://example.com",
        provider="dummy",
        amount="5.00",
        currency="EUR",
        state="succeeded",
    )
    d = p.to_dict()
    assert d["session_id"] == "s2"
    assert d["state"] == "succeeded"
    assert d["currency"] == "EUR"


# ---------------------------------------------------------------------------
# DB-backed store
# ---------------------------------------------------------------------------


def test_save_session_to_db(sqla_client, sqla_app, sqla_db):
    """Checkout saves a Payment row to the database."""
    with sqla_app.app_context():
        resp = sqla_client.post(
            "/merchants/checkout",
            json={"amount": "10.00", "currency": "USD"},
        )
        assert resp.status_code == 200
        session_id = resp.get_json()["session_id"]

        record = sqla_db.session.query(Payment).filter_by(session_id=session_id).first()
        assert record is not None
        assert record.state == "pending"
        assert record.amount == Decimal("10.00")


def test_save_session_stores_request_payload(sqla_client, sqla_app, sqla_db):
    """Checkout stores the request payload as JSON in request_payload."""
    with sqla_app.app_context():
        resp = sqla_client.post(
            "/merchants/checkout",
            json={"amount": "7.00", "currency": "EUR"},
        )
        assert resp.status_code == 200
        session_id = resp.get_json()["session_id"]

        record = sqla_db.session.query(Payment).filter_by(session_id=session_id).first()
        assert record is not None
        assert record.request_payload["amount"] == "7.00"
        assert record.request_payload["currency"] == "EUR"


def test_save_session_stores_response_payload(sqla_client, sqla_app, sqla_db):
    """Checkout stores the provider response as JSON in response_payload."""
    with sqla_app.app_context():
        resp = sqla_client.post(
            "/merchants/checkout",
            json={"amount": "3.00", "currency": "USD"},
        )
        assert resp.status_code == 200
        session_id = resp.get_json()["session_id"]

        record = sqla_db.session.query(Payment).filter_by(session_id=session_id).first()
        assert record is not None
        # DummyProvider returns {"simulated": True}; response_payload is already a dict
        assert isinstance(record.response_payload, dict)


def test_update_state_in_db(sqla_client, sqla_app, sqla_db, sqla_ext):
    """update_state writes the new state to the database row."""
    with sqla_app.app_context():
        resp = sqla_client.post(
            "/merchants/checkout",
            json={"amount": "5.00", "currency": "USD"},
        )
        session_id = resp.get_json()["session_id"]

        sqla_ext.update_state(session_id, "succeeded")

        record = sqla_db.session.query(Payment).filter_by(session_id=session_id).first()
        assert record.state == "succeeded"


def test_all_sessions_from_db(sqla_client, sqla_app, sqla_ext):
    """all_sessions returns rows from the database."""
    with sqla_app.app_context():
        sqla_client.post("/merchants/checkout", json={"amount": "1.00", "currency": "USD"})
        sessions = sqla_ext.all_sessions()
        assert len(sessions) >= 1
        assert all("session_id" in s for s in sessions)


# ---------------------------------------------------------------------------
# Admin ModelView
# ---------------------------------------------------------------------------


def test_admin_payment_list(sqla_client, sqla_app):
    """Admin payment list renders."""
    with sqla_app.app_context():
        resp = sqla_client.get("/admin/payments/")
        assert resp.status_code == 200


def test_admin_list_shows_payment(sqla_client, sqla_app):
    """Admin list shows a created payment."""
    with sqla_app.app_context():
        sqla_client.post("/merchants/checkout", json={"amount": "9.99", "currency": "USD"})
        resp = sqla_client.get("/admin/payments/")
        assert resp.status_code == 200
        assert b"dummy_sess_" in resp.data


# ---------------------------------------------------------------------------
# on_model_change validation
# ---------------------------------------------------------------------------


def test_on_model_change_valid_state(sqla_app, sqla_db):
    """on_model_change accepts valid states without raising."""
    from flask_merchants.contrib.sqla import PaymentModelView

    with sqla_app.app_context():
        view = PaymentModelView(Payment, sqla_db.session, name="P", endpoint="ptest")
        p = Payment(
            session_id="test1",
            redirect_url="http://x",
            provider="dummy",
            amount="1.00",
            currency="USD",
            state="succeeded",
        )
        view.on_model_change(None, p, is_created=False)  # should not raise


def test_on_model_change_invalid_state(sqla_app, sqla_db):
    """on_model_change raises ValidationError for unknown states."""
    from wtforms import ValidationError

    from flask_merchants.contrib.sqla import PaymentModelView

    with sqla_app.app_context():
        view = PaymentModelView(Payment, sqla_db.session, name="Q", endpoint="qtest")
        p = Payment(
            session_id="test2",
            redirect_url="http://x",
            provider="dummy",
            amount="1.00",
            currency="USD",
            state="pending",
        )
        # Write directly to __dict__ to bypass the SQLAlchemy InstrumentedAttribute
        # descriptor (a data descriptor that triggers @validates on __set__) so we
        # can test the on_model_change guard in isolation from @validates.
        p.__dict__["state"] = "invalid_state"
        with pytest.raises((ValidationError, ValueError)):
            view.on_model_change(None, p, is_created=False)


def test_validates_state_rejects_invalid():
    """PaymentMixin @validates raises ValueError for an unknown state."""
    with pytest.raises(ValueError, match="invalid_state"):
        Payment(
            session_id="vtest",
            redirect_url="http://x",
            provider="dummy",
            amount="1.00",
            currency="USD",
            state="invalid_state",
        )


def test_validates_state_accepts_valid():
    """PaymentMixin @validates accepts all recognised lifecycle states."""
    from flask_merchants.models import PaymentMixin

    for state in PaymentMixin.VALID_STATES:
        p = Payment(
            session_id=f"v-{state}",
            redirect_url="http://x",
            provider="dummy",
            amount="1.00",
            currency="USD",
            state=state,
        )
        assert p.state == state


# ---------------------------------------------------------------------------
# Bulk actions
# ---------------------------------------------------------------------------


def test_action_refund(sqla_client, sqla_app, sqla_db, sqla_ext):
    """Refund action marks payment rows as refunded."""
    with sqla_app.app_context():
        resp = sqla_client.post("/merchants/checkout", json={"amount": "1.00", "currency": "USD"})
        session_id = resp.get_json()["session_id"]

        record = sqla_db.session.query(Payment).filter_by(session_id=session_id).first()
        pk = str(record.id)

        action_resp = sqla_client.post(
            "/admin/payments/action/",
            data={"action": "refund", "rowid": pk},
        )
        # Flask-Admin redirects after action
        assert action_resp.status_code in (200, 302)

        sqla_db.session.expire_all()
        refreshed = sqla_db.session.query(Payment).filter_by(session_id=session_id).first()
        assert refreshed.state == "refunded"


def test_action_cancel(sqla_client, sqla_app, sqla_db, sqla_ext):
    """Cancel action marks payment rows as cancelled."""
    with sqla_app.app_context():
        resp = sqla_client.post("/merchants/checkout", json={"amount": "1.00", "currency": "USD"})
        session_id = resp.get_json()["session_id"]

        record = sqla_db.session.query(Payment).filter_by(session_id=session_id).first()
        pk = str(record.id)

        action_resp = sqla_client.post(
            "/admin/payments/action/",
            data={"action": "cancel", "rowid": pk},
        )
        assert action_resp.status_code in (200, 302)

        sqla_db.session.expire_all()
        refreshed = sqla_db.session.query(Payment).filter_by(session_id=session_id).first()
        assert refreshed.state == "cancelled"


def test_action_sync(sqla_client, sqla_app, sqla_db, sqla_ext):
    """Sync action fetches live state from the provider."""
    with sqla_app.app_context():
        resp = sqla_client.post("/merchants/checkout", json={"amount": "1.00", "currency": "USD"})
        session_id = resp.get_json()["session_id"]

        record = sqla_db.session.query(Payment).filter_by(session_id=session_id).first()
        assert record.state == "pending"
        pk = str(record.id)

        action_resp = sqla_client.post(
            "/admin/payments/action/",
            data={"action": "sync", "rowid": pk},
        )
        assert action_resp.status_code in (200, 302)

        sqla_db.session.expire_all()
        refreshed = sqla_db.session.query(Payment).filter_by(session_id=session_id).first()
        # DummyProvider returns a terminal state
        assert refreshed.state != "pending"


# ---------------------------------------------------------------------------
# Expanded form columns / create support
# ---------------------------------------------------------------------------


def test_payment_model_view_can_create():
    """PaymentModelView defaults to can_create=True."""
    from flask_merchants.contrib.sqla import PaymentModelView

    assert PaymentModelView.can_create is True


def test_payment_model_view_form_create_columns():
    """PaymentModelView exposes the expected create-form columns."""
    from flask_merchants.contrib.sqla import PaymentModelView

    assert "session_id" in PaymentModelView.form_create_columns
    assert "redirect_url" in PaymentModelView.form_create_columns
    assert "provider" in PaymentModelView.form_create_columns
    assert "amount" in PaymentModelView.form_create_columns
    assert "currency" in PaymentModelView.form_create_columns
    assert "state" in PaymentModelView.form_create_columns


def test_payment_model_view_form_edit_columns():
    """PaymentModelView exposes the expected edit-form columns (no session_id)."""
    from flask_merchants.contrib.sqla import PaymentModelView

    assert "redirect_url" in PaymentModelView.form_edit_columns
    assert "provider" in PaymentModelView.form_edit_columns
    assert "amount" in PaymentModelView.form_edit_columns
    assert "currency" in PaymentModelView.form_edit_columns
    assert "state" in PaymentModelView.form_edit_columns
    # session_id should not be editable after creation
    assert "session_id" not in PaymentModelView.form_edit_columns


def test_admin_create_page_renders(sqla_client, sqla_app):
    """Admin payment create page renders successfully."""
    with sqla_app.app_context():
        resp = sqla_client.get("/admin/payments/new/")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Configurable constructor kwargs
# ---------------------------------------------------------------------------


def test_can_create_kwarg_disables_create(sqla_app, sqla_db):
    """Passing can_create=False at construction disables create on that instance."""
    with sqla_app.app_context():
        view = PaymentModelView(
            Payment,
            sqla_db.session,
            name="NoCr",
            endpoint="nocr",
            can_create=False,
        )
        assert view.can_create is False
        # Class-level default must remain unchanged.
        assert PaymentModelView.can_create is True


def test_can_edit_kwarg_disables_edit(sqla_app, sqla_db):
    """Passing can_edit=False at construction disables editing on that instance."""
    with sqla_app.app_context():
        view = PaymentModelView(
            Payment,
            sqla_db.session,
            name="NoEd",
            endpoint="noed",
            can_edit=False,
        )
        assert view.can_edit is False
        assert PaymentModelView.can_edit is True


def test_can_delete_kwarg_enables_delete(sqla_app, sqla_db):
    """Passing can_delete=True enables deletion on that instance."""
    with sqla_app.app_context():
        view = PaymentModelView(
            Payment,
            sqla_db.session,
            name="Del",
            endpoint="del_test",
            can_delete=True,
        )
        assert view.can_delete is True


def test_constructor_kwargs_do_not_affect_class(sqla_app, sqla_db):
    """Instance overrides from constructor kwargs must not bleed into the class."""
    with sqla_app.app_context():
        PaymentModelView(
            Payment,
            sqla_db.session,
            name="Iso",
            endpoint="iso",
            can_create=False,
            can_edit=False,
        )
        # Class defaults must be untouched.
        assert PaymentModelView.can_create is True
        assert PaymentModelView.can_edit is True
