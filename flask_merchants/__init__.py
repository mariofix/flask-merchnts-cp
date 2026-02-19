"""flask_merchants – Flask extension for the merchants hosted-checkout SDK."""

from __future__ import annotations

from typing import Any

import merchants
from merchants.providers.dummy import DummyProvider

from flask_merchants.views import create_blueprint

from flask_merchants.version import __version__
__all__ = ["FlaskMerchants"]


class FlaskMerchants:
    """Flask extension that wires the *merchants* SDK into a Flask application.

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

    Configuration keys (set on ``app.config``):

    ``MERCHANTS_PROVIDER``
        String key of a pre-registered provider (default: ``"dummy"``).
        Ignored when *provider* is supplied directly.
    ``MERCHANTS_WEBHOOK_SECRET``
        HMAC-SHA256 secret used to verify incoming webhook signatures.
        When ``None`` (default) signature verification is skipped.
    ``MERCHANTS_URL_PREFIX``
        URL prefix for the blueprint (default: ``"/merchants"``).
    """

    def __init__(self, app=None, *, provider=None) -> None:
        self._provider = provider
        self._client: merchants.Client | None = None
        # Simple in-memory payment store: {payment_id: dict}
        self._store: dict[str, dict[str, Any]] = {}

        if app is not None:
            self.init_app(app)

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def init_app(self, app) -> None:
        """Initialise the extension against *app*."""
        provider = self._provider or DummyProvider()
        self._client = merchants.Client(provider=provider)

        app.config.setdefault("MERCHANTS_WEBHOOK_SECRET", None)
        app.config.setdefault("MERCHANTS_URL_PREFIX", "/merchants")

        blueprint = create_blueprint(self)
        url_prefix = app.config["MERCHANTS_URL_PREFIX"]
        app.register_blueprint(blueprint, url_prefix=url_prefix)

        app.extensions["merchants"] = self

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def client(self) -> merchants.Client:
        """The underlying :class:`merchants.Client` instance."""
        if self._client is None:
            raise RuntimeError(
                "FlaskMerchants extension not initialised. Call init_app(app) first."
            )
        return self._client

    # ------------------------------------------------------------------
    # Payment store helpers (simple in-memory; replace for production)
    # ------------------------------------------------------------------

    def save_session(self, session: merchants.CheckoutSession) -> None:
        """Persist a :class:`~merchants.CheckoutSession` in the store."""
        self._store[session.session_id] = {
            "session_id": session.session_id,
            "redirect_url": session.redirect_url,
            "provider": session.provider,
            "amount": str(session.amount),
            "currency": session.currency,
            "metadata": session.metadata,
            "state": "pending",
        }

    def get_session(self, payment_id: str) -> dict[str, Any] | None:
        """Return stored data for *payment_id*, or ``None``."""
        return self._store.get(payment_id)

    def update_state(self, payment_id: str, state: str) -> bool:
        """Update the stored state for *payment_id*. Returns ``True`` on success."""
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

    def all_sessions(self) -> list[dict[str, Any]]:
        """Return all stored payment sessions."""
        return list(self._store.values())
