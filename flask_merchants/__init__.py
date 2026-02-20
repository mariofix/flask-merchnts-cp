"""flask_merchants – Flask/Quart extension for the merchants hosted-checkout SDK."""

from __future__ import annotations

from typing import Any

import merchants
from merchants.providers.dummy import DummyProvider

from flask_merchants.views import create_blueprint
from flask_merchants.version import __version__

__all__ = ["FlaskMerchants"]




def _is_quart_app(app) -> bool:
    """Return ``True`` when *app* is a :class:`quart.Quart` instance."""
    try:
        from quart import Quart

        return isinstance(app, Quart)
    except ImportError:
        return False


class FlaskMerchants:
    """Flask/Quart extension that wires the *merchants* SDK into an application.

    Usage – application factory pattern::

        from flask import Flask
        from flask_merchants import FlaskMerchants

        merchants_ext = FlaskMerchants()

        def create_app():
            app = Flask(__name__)
            merchants_ext.init_app(app)
            return app

    Usage – direct initialisation::

        from flask import Flask
        from flask_merchants import FlaskMerchants

        app = Flask(__name__)
        ext = FlaskMerchants(app)

    Usage – with SQLAlchemy (Flask-SQLAlchemy 3.x)::

        from flask import Flask
        from flask_sqlalchemy import SQLAlchemy
        from flask_merchants import FlaskMerchants
        from flask_merchants.models import Base

        db = SQLAlchemy(model_class=Base)
        app = Flask(__name__)
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///payments.db"
        ext = FlaskMerchants(app, db=db)
        db.init_app(app)

    Usage – with a single custom SQLAlchemy model::

        from flask import Flask
        from flask_sqlalchemy import SQLAlchemy
        from sqlalchemy import Integer
        from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
        from flask_merchants import FlaskMerchants
        from flask_merchants.models import PaymentMixin

        class Base(DeclarativeBase):
            pass

        db = SQLAlchemy(model_class=Base)

        class Pagos(PaymentMixin, db.Model):
            __tablename__ = "pagos"
            id: Mapped[int] = mapped_column(Integer, primary_key=True)

        app = Flask(__name__)
        ext = FlaskMerchants(app, db=db, models=[Pagos])

    Usage – with multiple custom SQLAlchemy models in the same app::

        class Pagos(PaymentMixin, db.Model):
            __tablename__ = "pagos"
            id: Mapped[int] = mapped_column(Integer, primary_key=True)

        class Paiements(PaymentMixin, db.Model):
            __tablename__ = "paiements"
            id: Mapped[int] = mapped_column(Integer, primary_key=True)

        ext = FlaskMerchants(app, db=db, models=[Pagos, Paiements])

        # Direct a checkout to a specific model:
        session = ext.client.payments.create_checkout(...)
        ext.save_session(session, model_class=Pagos)
        ext.save_session(session2, model_class=Paiements)

        # get_session / update_state search across all models automatically.
        # all_sessions() returns records from all models combined.
        # all_sessions(model_class=Pagos) returns only Pagos records.

    Usage – with Quart (async)::

        from quart import Quart
        from flask_merchants import FlaskMerchants

        app = Quart(__name__)
        ext = FlaskMerchants(app)   # async blueprint selected automatically

    Configuration keys (set on ``app.config``):

    ``MERCHANTS_WEBHOOK_SECRET``
        HMAC-SHA256 secret used to verify incoming webhook signatures.
        When ``None`` (default) signature verification is skipped.
    ``MERCHANTS_URL_PREFIX``
        URL prefix for the blueprint (default: ``"/merchants"``).

    Multiple providers example::

        from merchants.providers.dummy import DummyProvider

        ext = FlaskMerchants(app, providers=[DummyProvider(), DummyProvider(base_url="https://other.example.com")])

        # In checkout, pass ``provider`` field to select the provider:
        # POST /merchants/checkout  {"amount": "9.99", "currency": "USD", "provider": "dummy"}

    """

    def __init__(self, app=None, *, provider=None, providers=None, db=None, models=None) -> None:
        self._provider = provider
        self._providers: list = list(providers) if providers is not None else []
        self._db = db
        self._models: list = list(models) if models is not None else []
        self._client: merchants.Client | None = None
        # Dict of clients keyed by provider key string.
        self._clients: dict[str, merchants.Client] = {}
        # Simple in-memory payment store: {payment_id: dict}
        # Used when no SQLAlchemy db is provided.
        self._store: dict[str, dict[str, Any]] = {}

        if app is not None:
            self.init_app(app)

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def init_app(self, app) -> None:
        """Initialise the extension against *app* (Flask or Quart)."""
        # Build the ordered list of providers
        all_providers: list = list(self._providers)
        if self._provider is not None:
            # Single-provider shortcut takes precedence as the default
            all_providers.insert(0, self._provider)
        if not all_providers:
            all_providers = [DummyProvider()]

        # Create one Client per provider, keyed by provider.key
        self._clients = {p.key: merchants.Client(provider=p) for p in all_providers}
        # Default client is the first registered provider
        self._client = next(iter(self._clients.values()))

        app.config.setdefault("MERCHANTS_WEBHOOK_SECRET", None)
        app.config.setdefault("MERCHANTS_URL_PREFIX", "/merchants")

        if _is_quart_app(app):
            from flask_merchants.quart_views import create_async_blueprint

            blueprint = create_async_blueprint(self)
        else:
            blueprint = create_blueprint(self)

        url_prefix = app.config["MERCHANTS_URL_PREFIX"]
        app.register_blueprint(blueprint, url_prefix=url_prefix)

        app.extensions["merchants"] = self

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def client(self) -> merchants.Client:
        """The underlying :class:`merchants.Client` instance (default provider)."""
        if self._client is None:
            raise RuntimeError(
                "FlaskMerchants extension not initialised. Call init_app(app) first."
            )
        return self._client

    def list_providers(self) -> list[str]:
        """Return a list of registered provider key strings."""
        return list(self._clients.keys())

    def get_client(self, provider_key: str | None = None) -> merchants.Client:
        """Return the :class:`merchants.Client` for *provider_key*.

        When *provider_key* is ``None`` (or omitted) the default client
        (first registered provider) is returned.

        Raises:
            KeyError: If *provider_key* is not registered.
        """
        if provider_key is None:
            return self.client
        if provider_key not in self._clients:
            raise KeyError(f"Unknown provider: {provider_key!r}")
        return self._clients[provider_key]

    def _get_model_classes(self) -> list:
        """Return the list of all registered model classes.

        Falls back to the built-in :class:`~flask_merchants.models.Payment`
        when no custom models have been registered.
        """
        if self._models:
            return self._models
        from flask_merchants.models import Payment
        return [Payment]

    @property
    def _payment_model(self):
        """Return the *default* model class (first in the list)."""
        return self._get_model_classes()[0]

    # ------------------------------------------------------------------
    # Payment store helpers
    # ------------------------------------------------------------------

    def save_session(
        self,
        session: merchants.CheckoutSession,
        *,
        model_class=None,
        request_payload: dict | None = None,
    ) -> None:
        """Persist a :class:`~merchants.CheckoutSession`.

        When a SQLAlchemy *db* was provided the record is saved to the
        database; otherwise it is kept in the in-memory store.

        Args:
            session: The checkout session to persist.
            model_class: The model class to store the record in.
                Defaults to the first registered model (or the built-in
                :class:`~flask_merchants.models.Payment`).  Use this when
                you have multiple models registered and need to direct a
                payment to a specific table.
            request_payload: The data dict that was sent to the provider.
                When provided it is serialised as JSON and stored on the
                record.  Defaults to an empty dict.
        """
        # session.raw holds the provider's raw response; guard against non-dict types
        response_raw = session.raw if isinstance(session.raw, dict) else {}
        req_payload = request_payload or {}

        data = {
            "session_id": session.session_id,
            "redirect_url": session.redirect_url,
            "provider": session.provider,
            "amount": str(session.amount),
            "currency": session.currency,
            "metadata": session.metadata,
            "state": "pending",
            "request_payload": req_payload,
            "response_payload": response_raw,
        }

        if self._db is not None:
            cls = model_class if model_class is not None else self._payment_model
            record = cls(
                session_id=session.session_id,
                redirect_url=session.redirect_url,
                provider=session.provider,
                amount=session.amount,
                currency=session.currency,
                state="pending",
                metadata_json=session.metadata or {},
                request_payload=req_payload,
                response_payload=response_raw,
            )
            self._db.session.add(record)
            self._db.session.commit()

        # Always keep in-memory copy for fast look-up
        self._store[session.session_id] = data

    def get_session(self, payment_id: str) -> dict[str, Any] | None:
        """Return stored data for *payment_id*, or ``None``.

        When multiple models are registered, all of them are searched in
        registration order and the first match is returned.
        """
        if self._db is not None:
            for model_cls in self._get_model_classes():
                record = (
                    self._db.session.query(model_cls)
                    .filter_by(session_id=payment_id)
                    .first()
                )
                if record is not None:
                    return record.to_dict()
            return None
        return self._store.get(payment_id)

    def update_state(self, payment_id: str, state: str) -> bool:
        """Update the stored state for *payment_id*. Returns ``True`` on success.

        When multiple models are registered, all of them are searched in
        registration order; the first match is updated.
        """
        if self._db is not None:
            for model_cls in self._get_model_classes():
                record = (
                    self._db.session.query(model_cls)
                    .filter_by(session_id=payment_id)
                    .first()
                )
                if record is not None:
                    record.state = state
                    self._db.session.commit()
                    if payment_id in self._store:
                        self._store[payment_id]["state"] = state
                    return True
            # Not found in any model – fall back to in-memory
            if payment_id not in self._store:
                return False
            self._store[payment_id]["state"] = state
            return True

        if payment_id not in self._store:
            return False
        self._store[payment_id]["state"] = state
        return True

    def refund_session(self, payment_id: str) -> bool:
        """Mark *payment_id* as refunded. Returns ``True`` on success."""
        return self.update_state(payment_id, "refunded")

    def cancel_session(self, payment_id: str) -> bool:
        """Mark *payment_id* as cancelled. Returns ``True`` on success."""
        return self.update_state(payment_id, "cancelled")

    def sync_from_provider(self, payment_id: str) -> dict[str, Any] | None:
        """Fetch live status from the provider and update the stored state.

        Returns the updated stored record, or ``None`` if *payment_id* is not
        found or the provider call fails.
        """
        stored = self.get_session(payment_id)
        if stored is None:
            return None
        try:
            status = self.client.payments.get(payment_id)
        except Exception:  # noqa: BLE001
            return None
        self.update_state(payment_id, status.state.value)
        stored["state"] = status.state.value
        return stored

    def all_sessions(self, *, model_class=None) -> list[dict[str, Any]]:
        """Return all stored payment sessions.

        Args:
            model_class: When provided, return records only from that model
                class.  When omitted, records from **all** registered models
                are returned combined.
        """
        if self._db is not None:
            classes = [model_class] if model_class is not None else self._get_model_classes()
            result = []
            for cls in classes:
                result.extend(r.to_dict() for r in self._db.session.query(cls).all())
            return result
        return list(self._store.values())

