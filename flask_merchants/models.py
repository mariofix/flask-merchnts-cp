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

Or with an existing ``db`` that uses a custom model class, register the
``Payment`` mapper explicitly::

    from flask_merchants.models import Payment
    # Payment is bound to its own Base; Flask-SQLAlchemy discovers it
    # automatically when you pass ``metadata=Base.metadata`` to SQLAlchemy().
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared declarative base for flask-merchants models."""


class Payment(Base):
    """Persistent payment session record.

    Attributes:
        id: Auto-incrementing primary key.
        session_id: Provider-issued session/payment ID (unique).
        redirect_url: Hosted-checkout URL the user was redirected to.
        provider: Provider key string (e.g. ``"dummy"``, ``"stripe"``).
        amount: Payment amount stored as a decimal string (e.g. ``"19.99"``).
        currency: ISO-4217 currency code (e.g. ``"USD"``).
        state: Payment lifecycle state (``"pending"``, ``"succeeded"``, …).
        metadata_json: JSON-serialised metadata dict passed at checkout.
        created_at: Record creation timestamp (UTC).
        updated_at: Record last-update timestamp (UTC).
    """

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    redirect_url: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(64))
    amount: Mapped[str] = mapped_column(String(32))
    currency: Mapped[str] = mapped_column(String(8))
    state: Mapped[str] = mapped_column(String(32), default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
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
        return f"<Payment {self.session_id} state={self.state!r}>"

    def to_dict(self) -> dict:
        """Return a plain-dict representation (mirrors the in-memory store format)."""
        import json as _json
        try:
            metadata = _json.loads(self.metadata_json) if self.metadata_json else {}
        except (ValueError, TypeError):
            metadata = {}
        return {
            "session_id": self.session_id,
            "redirect_url": self.redirect_url,
            "provider": self.provider,
            "amount": self.amount,
            "currency": self.currency,
            "state": self.state,
            "metadata": metadata,
        }
