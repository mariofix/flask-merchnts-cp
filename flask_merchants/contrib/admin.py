"""Flask-Admin views for managing payments stored by flask-merchants.

Install the optional dependency before using this module::

    pip install "flask-merchants[admin]"

Example::

    from flask import Flask
    from flask_admin import Admin
    from flask_merchants import FlaskMerchants
    from flask_merchants.contrib.admin import PaymentView

    app = Flask(__name__)
    ext = FlaskMerchants(app)

    admin = Admin(app, name="My Shop")
    admin.add_view(PaymentView(ext, name="Payments", endpoint="payments"))
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
