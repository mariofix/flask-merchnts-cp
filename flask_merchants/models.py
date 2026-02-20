"""SQLAlchemy ORM model for flask-merchants payments.

Usage with Flask-SQLAlchemy 3.x::

    from flask import Flask
    from flask_sqlalchemy import SQLAlchemy
    from flask_merchants.models import Base, Payment

    db = SQLAlchemy(model_class=Base)

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///payments.db"
    db.init_app(app)

    with app.app_context():
        db.create_all()

Or bring your own model by mixing in :class:`PaymentMixin`::

    from flask_sqlalchemy import SQLAlchemy
    from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
    from sqlalchemy import Integer
    from flask_merchants.models import PaymentMixin

    class Base(DeclarativeBase):
        pass

    db = SQLAlchemy(model_class=Base)

    class Pagos(PaymentMixin, db.Model):
        __tablename__ = "pagos"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)

Then pass the model to FlaskMerchants::

    ext = FlaskMerchants(app, db=db, model=Pagos)
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class PaymentMixin:
    """SQLAlchemy declarative mixin that adds all payment fields.

    Mix this into your own model class so that flask-merchants can store
    and retrieve payments using your table instead of the built-in
    :class:`Payment` model::

        class Pagos(PaymentMixin, db.Model):
            __tablename__ = "pagos"
            id: Mapped[int] = mapped_column(Integer, primary_key=True)

    All column definitions, :meth:`to_dict`, and :meth:`__repr__` are
    inherited from this mixin.  You can add extra columns or relationships
    as normal.
    """

    session_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    redirect_url: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(64))
    amount: Mapped[str] = mapped_column(String(32))
    currency: Mapped[str] = mapped_column(String(8))
    state: Mapped[str] = mapped_column(String(32), default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    request_payload: Mapped[str] = mapped_column(Text, default="{}")
    response_payload: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.session_id} state={self.state!r}>"

    def to_dict(self) -> dict:
        """Return a plain-dict representation (mirrors the in-memory store format)."""
        import json as _json

        def _parse(value: str) -> dict:
            try:
                return _json.loads(value) if value else {}
            except (ValueError, TypeError):
                return {}

        return {
            "session_id": self.session_id,
            "redirect_url": self.redirect_url,
            "provider": self.provider,
            "amount": self.amount,
            "currency": self.currency,
            "state": self.state,
            "metadata": _parse(self.metadata_json),
            "request_payload": _parse(self.request_payload),
            "response_payload": _parse(self.response_payload),
        }


class Base(DeclarativeBase):
    """Shared declarative base for flask-merchants models."""


class Payment(PaymentMixin, Base):
    """Built-in payment record backed by the ``payments`` table.

    Attributes:
        id: Auto-incrementing primary key.
        session_id: Provider-issued session/payment ID (unique).
        redirect_url: Hosted-checkout URL the user was redirected to.
        provider: Provider key string (e.g. ``"dummy"``, ``"stripe"``).
        amount: Payment amount stored as a decimal string (e.g. ``"19.99"``).
        currency: ISO-4217 currency code (e.g. ``"USD"``).
        state: Payment lifecycle state (``"pending"``, ``"succeeded"``, …).
        metadata_json: JSON-serialised metadata dict passed at checkout.
        request_payload: JSON-serialised data sent to the provider.
        response_payload: JSON-serialised raw response received from the provider.
        created_at: Record creation timestamp (UTC).
        updated_at: Record last-update timestamp (UTC).
    """

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
