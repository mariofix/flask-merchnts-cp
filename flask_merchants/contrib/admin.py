"""Flask-Admin views for managing payments stored by flask-merchants.

Install the optional dependency before using this module::

    pip install "flask-merchants[admin]"

Example – manual registration::

    from flask import Flask
    from flask_admin import Admin
    from flask_merchants import FlaskMerchants
    from flask_merchants.contrib.admin import PaymentView, ProvidersView

    app = Flask(__name__)
    ext = FlaskMerchants(app)

    admin = Admin(app, name="My Shop")
    admin.add_view(PaymentView(ext, name="Payments", endpoint="payments"))
    admin.add_view(ProvidersView(ext, name="Providers", endpoint="providers"))

Example – automatic registration (pass ``admin=`` to FlaskMerchants)::

    from flask import Flask
    from flask_admin import Admin
    from flask_merchants import FlaskMerchants

    app = Flask(__name__)
    admin = Admin(app, name="My Shop")
    ext = FlaskMerchants(app, admin=admin)
    # PaymentView and ProvidersView are automatically added under category="Merchants"
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

try:
    from flask_admin import BaseView, expose
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "flask-admin is required for flask_merchants.contrib.admin. "
        "Install it with: pip install 'flask-merchants[admin]'"
    ) from exc

if TYPE_CHECKING:
    from flask_merchants import FlaskMerchants


def _mask_secret(value: str) -> str:
    """Return *value* with all but the first 5 and last 1 characters masked.

    Short values (6 characters or fewer) are replaced entirely with ``"***"``
    to avoid leaking meaningful content through the masking pattern.

    Examples::

        _mask_secret("sk_test_1234567890")  # -> "sk_te…0"
        _mask_secret("short")               # -> "***"
    """
    if len(value) <= 6:
        return "***"
    return value[:5] + "…" + value[-1]


def _get_auth_info(auth) -> dict[str, str]:
    """Extract and mask auth details from an :class:`~merchants.auth.AuthStrategy`.

    Returns a dict with ``type``, ``header``, and ``masked_value`` keys.
    When *auth* is ``None`` an empty/unauthenticated descriptor is returned.
    """
    if auth is None:
        return {"type": "None", "header": "—", "masked_value": "—"}

    auth_type = type(auth).__name__
    # ApiKeyAuth stores the key in _api_key; TokenAuth in _token
    raw = getattr(auth, "_api_key", None) or getattr(auth, "_token", None) or ""
    header = getattr(auth, "_header", "—")
    return {
        "type": auth_type,
        "header": str(header),
        "masked_value": _mask_secret(raw) if raw else "—",
    }


_STATE_CHOICES = [
    ("pending", "Pending"),
    ("processing", "Processing"),
    ("succeeded", "Succeeded"),
    ("failed", "Failed"),
    ("cancelled", "Cancelled"),
    ("refunded", "Refunded"),
    ("unknown", "Unknown"),
]


class PaymentView(BaseView):
    """Flask-Admin view that lists all stored payments and allows managing them.

    Provides:
    - List of all stored payment sessions.
    - Update state via dropdown.
    - Dedicated Refund action.
    - Dedicated Cancel action.
    - Sync from Provider action (fetches live status from the payment provider).

    Args:
        ext: Initialised :class:`~flask_merchants.FlaskMerchants` extension instance.
        name: Display name shown in the admin navigation bar.
        endpoint: Internal Flask endpoint prefix (must be unique).
        category: Optional admin category/group name.
    """

    def __init__(
        self,
        ext: "FlaskMerchants",
        name: str = "Payments",
        endpoint: str = "payments",
        category: str | None = None,
        **kwargs: Any,
    ) -> None:
        self._ext = ext
        super().__init__(name=name, endpoint=endpoint, category=category, **kwargs)

    @expose("/")
    def index(self):
        """List all stored payment sessions."""
        payments = self._ext.all_sessions()
        return self.render(
            "flask_merchants/admin/payments_list.html",
            payments=payments,
            state_choices=_STATE_CHOICES,
        )

    @expose("/update", methods=["POST"])
    def update(self):
        """Update the stored state of a payment via the dropdown."""
        from flask import flash, redirect, request, url_for

        payment_id = request.form.get("payment_id", "").strip()
        new_state = request.form.get("state", "").strip()

        if not payment_id or not new_state:
            flash("Invalid form submission.", "danger")
        elif self._ext.update_state(payment_id, new_state):
            flash(f"Payment {payment_id} updated to '{new_state}'.", "success")
        else:
            flash(f"Payment {payment_id} not found.", "danger")

        return redirect(url_for(".index"))

    @expose("/refund", methods=["POST"])
    def refund(self):
        """Mark a payment as refunded."""
        from flask import flash, redirect, request, url_for

        payment_id = request.form.get("payment_id", "").strip()

        if not payment_id:
            flash("Invalid form submission.", "danger")
        elif self._ext.refund_session(payment_id):
            flash(f"Payment {payment_id} marked as refunded.", "success")
        else:
            flash(f"Payment {payment_id} not found.", "danger")

        return redirect(url_for(".index"))

    @expose("/cancel", methods=["POST"])
    def cancel(self):
        """Mark a payment as cancelled."""
        from flask import flash, redirect, request, url_for

        payment_id = request.form.get("payment_id", "").strip()

        if not payment_id:
            flash("Invalid form submission.", "danger")
        elif self._ext.cancel_session(payment_id):
            flash(f"Payment {payment_id} marked as cancelled.", "success")
        else:
            flash(f"Payment {payment_id} not found.", "danger")

        return redirect(url_for(".index"))

    @expose("/sync", methods=["POST"])
    def sync(self):
        """Fetch live payment status from the provider and update the stored state."""
        from flask import flash, redirect, request, url_for

        payment_id = request.form.get("payment_id", "").strip()

        if not payment_id:
            flash("Invalid form submission.", "danger")
        else:
            updated = self._ext.sync_from_provider(payment_id)
            if updated is None:
                flash(
                    f"Payment {payment_id} not found or provider call failed.", "danger"
                )
            else:
                flash(
                    f"Payment {payment_id} synced from provider: state is now '{updated['state']}'.",
                    "success",
                )

        return redirect(url_for(".index"))


class ProvidersView(BaseView):
    """Flask-Admin view that lists all payment providers registered with the application.

    Args:
        ext: Initialised :class:`~flask_merchants.FlaskMerchants` extension instance.
        name: Display name shown in the admin navigation bar.
        endpoint: Internal Flask endpoint prefix (must be unique).
        category: Optional admin category/group name.
    """

    def __init__(
        self,
        ext: "FlaskMerchants",
        name: str = "Providers",
        endpoint: str = "providers",
        category: str | None = None,
        **kwargs: Any,
    ) -> None:
        self._ext = ext
        super().__init__(name=name, endpoint=endpoint, category=category, **kwargs)

    @expose("/")
    def index(self):
        """List all registered payment providers with auth and payment stats."""
        import merchants as merchants_sdk

        provider_keys = merchants_sdk.list_providers()

        # Build a per-provider payment count from the store once.
        all_payments = self._ext.all_sessions()
        payment_counts: dict[str, int] = {}
        for p in all_payments:
            pkey = p.get("provider", "")
            payment_counts[pkey] = payment_counts.get(pkey, 0) + 1

        providers = []
        for key in provider_keys:
            try:
                client = self._ext.get_client(key)
                base_url = getattr(client._provider, "_base_url", "") or getattr(client, "_base_url", "N/A") or "N/A"
                auth_info = _get_auth_info(client._auth)
                transport = type(client._transport).__name__
            except Exception:  # noqa: BLE001
                base_url = "N/A"
                auth_info = _get_auth_info(None)
                transport = "N/A"

            providers.append(
                {
                    "key": key,
                    "base_url": base_url,
                    "auth_type": auth_info["type"],
                    "auth_header": auth_info["header"],
                    "auth_masked_value": auth_info["masked_value"],
                    "payment_count": payment_counts.get(key, 0),
                    "transport": transport,
                }
            )

        return self.render(
            "flask_merchants/admin/providers_list.html",
            providers=providers,
        )


def register_admin_views(admin, ext: "FlaskMerchants") -> None:
    """Register the standard Merchants admin views into *admin*.

    This registers :class:`PaymentView` and :class:`ProvidersView` under
    ``category="Merchants"``.  It is called automatically when you pass
    ``admin=`` to :class:`~flask_merchants.FlaskMerchants`::

        admin = Admin(app, name="My Shop")
        ext = FlaskMerchants(app, admin=admin)

    You can also call it manually if you need finer control::

        register_admin_views(admin, ext)

    Args:
        admin: A :class:`flask_admin.Admin` instance.
        ext: An initialised :class:`~flask_merchants.FlaskMerchants` instance.
    """
    admin.add_view(
        PaymentView(
            ext,
            name="Payments",
            endpoint="merchants_payments",
            category="Merchants",
        )
    )
    admin.add_view(
        ProvidersView(
            ext,
            name="Providers",
            endpoint="merchants_providers",
            category="Merchants",
        )
    )
