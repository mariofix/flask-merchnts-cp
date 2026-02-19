"""Flask-Admin views for managing payments stored by flask-merchants.

Install the optional dependency before using this module::

    pip install "flask-merchants[admin]"

Example::

    from flask import Flask
    from flask_admin import Admin
    from flask_merchants import Merchants
    from flask_merchants.contrib.admin import PaymentView

    app = Flask(__name__)
    ext = Merchants(app)

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
    from flask_merchants import Merchants


_STATE_CHOICES = [
    ("pending", "Pending"),
    ("processing", "Processing"),
    ("succeeded", "Succeeded"),
    ("failed", "Failed"),
    ("cancelled", "Cancelled"),
    ("refunded", "Refunded"),
    ("unknown", "Unknown"),
]

# Inline template to avoid external template file discovery issues.
_LIST_TEMPLATE = """\
{% extends 'admin/master.html' %}
{% block body %}
<div class="container-fluid">
  <h2>Payments</h2>
  {% with messages = get_flashed_messages(with_categories=true) %}
    {% for category, message in messages %}
      <div class="alert alert-{{ category }}">{{ message }}</div>
    {% endfor %}
  {% endwith %}
  <table class="table table-bordered table-striped">
    <thead>
      <tr>
        <th>Payment ID</th><th>Provider</th><th>Amount</th>
        <th>Currency</th><th>State</th><th>Actions</th>
      </tr>
    </thead>
    <tbody>
      {% for p in payments %}
      <tr>
        <td>{{ p.session_id }}</td>
        <td>{{ p.provider }}</td>
        <td>{{ p.amount }}</td>
        <td>{{ p.currency }}</td>
        <td>{{ p.state }}</td>
        <td>
          <form method="POST" action="{{ url_for('.update') }}" class="form-inline">
            <input type="hidden" name="payment_id" value="{{ p.session_id }}">
            <select name="state" class="form-control form-control-sm mr-1">
              {% for value, label in state_choices %}
              <option value="{{ value }}" {% if value == p.state %}selected{% endif %}>
                {{ label }}
              </option>
              {% endfor %}
            </select>
            <button type="submit" class="btn btn-sm btn-primary">Update</button>
          </form>
        </td>
      </tr>
      {% else %}
      <tr>
        <td colspan="6" class="text-center text-muted">No payments recorded yet.</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
"""


class PaymentView(BaseView):
    """Flask-Admin view that lists all stored payments and allows updating their state.

    Args:
        ext: Initialised :class:`~flask_merchants.Merchants` extension instance.
        name: Display name shown in the admin navigation bar.
        endpoint: Internal Flask endpoint prefix (must be unique).
        category: Optional admin category/group name.
    """

    def __init__(
        self,
        ext: "Merchants",
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
        """Update the stored state of a payment."""
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
