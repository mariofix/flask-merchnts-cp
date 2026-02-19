"""Blueprint with checkout, webhook, success and cancel routes."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import merchants
from flask import Blueprint, jsonify, redirect, request, url_for

if TYPE_CHECKING:
    from flask_merchants import FlaskMerchants


def create_blueprint(ext: "FlaskMerchants") -> Blueprint:
    """Return a Blueprint pre-configured with the extension instance."""

    bp = Blueprint("merchants", __name__, template_folder="templates")

    # ------------------------------------------------------------------
    # Checkout – initiate a payment
    # ------------------------------------------------------------------

    @bp.route("/checkout", methods=["GET", "POST"])
    def checkout():
        """Create a hosted-checkout session and redirect the user.

        Accepts JSON body **or** form fields:

        * ``amount`` – decimal string (e.g. ``"19.99"``)
        * ``currency`` – ISO-4217 code (e.g. ``"USD"``)
        * ``metadata`` – optional JSON object / form JSON string
        """
        data = request.get_json(silent=True) or request.form

        amount = data.get("amount", "1.00")
        currency = data.get("currency", "USD")
        raw_meta = data.get("metadata")
        if isinstance(raw_meta, str):
            try:
                metadata = json.loads(raw_meta)
            except (ValueError, TypeError):
                metadata = {}
        elif isinstance(raw_meta, dict):
            metadata = raw_meta
        else:
            metadata = {}

        success_url = url_for("merchants.success", _external=True)
        cancel_url = url_for("merchants.cancel", _external=True)

        try:
            session = ext.client.payments.create_checkout(
                amount=amount,
                currency=currency,
                success_url=success_url,
                cancel_url=cancel_url,
                metadata=metadata,
            )
        except merchants.UserError as exc:
            return jsonify({"error": str(exc)}), 400

        ext.save_session(session)

        if request.is_json:
            return jsonify(
                {
                    "session_id": session.session_id,
                    "redirect_url": session.redirect_url,
                }
            )
        return redirect(session.redirect_url)

    # ------------------------------------------------------------------
    # Success / cancel landing pages
    # ------------------------------------------------------------------

    @bp.route("/success")
    def success():
        """Landing page after a successful payment."""
        payment_id = request.args.get("payment_id", "")
        stored = ext.get_session(payment_id) if payment_id else None
        return jsonify(
            {
                "status": "success",
                "payment_id": payment_id or None,
                "stored": stored,
            }
        )

    @bp.route("/cancel")
    def cancel():
        """Landing page after a cancelled payment."""
        payment_id = request.args.get("payment_id", "")
        stored = ext.get_session(payment_id) if payment_id else None
        return jsonify(
            {
                "status": "cancelled",
                "payment_id": payment_id or None,
                "stored": stored,
            }
        )

    # ------------------------------------------------------------------
    # Payment status
    # ------------------------------------------------------------------

    @bp.route("/status/<payment_id>")
    def payment_status(payment_id: str):
        """Return the live payment status from the provider."""
        try:
            status = ext.client.payments.get(payment_id)
        except merchants.UserError as exc:
            return jsonify({"error": str(exc)}), 400

        ext.update_state(payment_id, status.state.value)

        return jsonify(
            {
                "payment_id": status.payment_id,
                "state": status.state.value,
                "provider": status.provider,
                "is_final": status.is_final,
                "is_success": status.is_success,
            }
        )

    # ------------------------------------------------------------------
    # Webhook
    # ------------------------------------------------------------------

    @bp.route("/webhook", methods=["POST"])
    def webhook():
        """Receive and process incoming provider webhook events.

        When ``MERCHANTS_WEBHOOK_SECRET`` is set on the app config the
        request signature is verified before processing.
        """
        from flask import current_app

        secret: str | None = current_app.config.get("MERCHANTS_WEBHOOK_SECRET")
        payload: bytes = request.get_data()
        headers: dict[str, str] = dict(request.headers)

        if secret:
            signature = headers.get("X-Merchants-Signature", "")
            try:
                merchants.verify_signature(
                    payload=payload,
                    secret=secret,
                    signature=signature,
                )
            except merchants.WebhookVerificationError:
                return jsonify({"error": "invalid signature"}), 400

        try:
            event = ext.client._provider.parse_webhook(payload, headers)
        except Exception:  # noqa: BLE001
            return jsonify({"error": "malformed payload"}), 400

        ext.update_state(event.payment_id, event.state.value)

        return jsonify(
            {
                "received": True,
                "event_id": event.event_id,
                "event_type": event.event_type,
                "payment_id": event.payment_id,
                "state": event.state.value,
            }
        )

    return bp
