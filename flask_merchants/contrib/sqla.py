"""Flask-Admin ModelView for the SQLAlchemy-backed Payment model.

Requires the ``db`` extra::

    pip install "flask-merchants[db]"

Example::

    from flask import Flask
    from flask_sqlalchemy import SQLAlchemy
    from flask_admin import Admin
    from flask_merchants import FlaskMerchants
    from flask_merchants.models import Base, Payment
    from flask_merchants.contrib.sqla import PaymentModelView

    db = SQLAlchemy(model_class=Base)

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///payments.db"
    app.config["SECRET_KEY"] = "change-me"

    ext = FlaskMerchants(app, db=db)
    db.init_app(app)

    admin = Admin(app, name="My Shop")
    admin.add_view(PaymentModelView(Payment, db.session, ext=ext, name="Payments"))

    with app.app_context():
        db.create_all()
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

try:
    from flask_admin.actions import action
    from flask_admin.contrib.sqla import ModelView
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "flask-admin and flask-sqlalchemy are required for "
        "flask_merchants.contrib.sqla. "
        "Install them with: pip install 'flask-merchants[db]'"
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


class PaymentModelView(ModelView):
    """Flask-Admin view for the :class:`~flask_merchants.models.Payment` model.

    Provides:
    - Searchable / filterable list of all payment records.
    - Create, view, and edit payment records (all user-editable fields).
    - State-change detection via SQLAlchemy attribute history in
      ``on_model_change``: only when the ``state`` field is actually
      modified are the extra state-transition checks applied.
    - Bulk **Refund**, **Cancel**, and **Sync from Provider** actions.

    Args:
        model: The :class:`~flask_merchants.models.Payment` model class.
        session: A SQLAlchemy scoped session (e.g. ``db.session``).
        ext: Optional :class:`~flask_merchants.FlaskMerchants` instance.
            Required only for the *Sync from Provider* action.
        name: Display name shown in the admin navigation bar.
        endpoint: Internal Flask endpoint prefix (must be unique).
        category: Optional admin category/group name.
    """

    # ------------------------------------------------------------------
    # Column configuration
    # ------------------------------------------------------------------
    column_list = [
        "session_id",
        "provider",
        "amount",
        "currency",
        "state",
        "created_at",
        "updated_at",
    ]
    column_searchable_list = ["session_id", "provider"]
    column_filters = ["state", "provider", "currency"]
    column_default_sort = ("created_at", True)

    # Allow creating new payment records from the admin UI.
    can_create = True

    # Fields available when creating a new payment.
    form_create_columns = [
        "session_id",
        "redirect_url",
        "provider",
        "amount",
        "currency",
        "state",
        "metadata_json",
    ]

    # Fields available when editing an existing payment.
    form_edit_columns = [
        "redirect_url",
        "provider",
        "amount",
        "currency",
        "state",
        "metadata_json",
    ]

    form_choices = {"state": _STATE_CHOICES}

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def __init__(self, model, session, *, ext: "FlaskMerchants | None" = None, **kwargs: Any) -> None:
        self._ext = ext
        super().__init__(model, session, **kwargs)

    # ------------------------------------------------------------------
    # on_model_change hook
    # ------------------------------------------------------------------

    def on_model_change(self, form, model, is_created: bool) -> None:
        """Detect state changes and validate the new state before committing.

        Uses SQLAlchemy's attribute history (``inspect(model).attrs.state.history``)
        to determine whether the ``state`` field was actually modified in this
        transaction.  When a state change is detected, the new value is validated
        against the recognised lifecycle states; if the value is invalid a
        :class:`wtforms.ValidationError` is raised so Flask-Admin rolls back the
        form and shows an inline error to the user.

        SQLAlchemy's ``@validates`` hook in :class:`~flask_merchants.models.PaymentMixin`
        provides the first line of defence at the ORM attribute level.  This
        hook adds a second layer that integrates with Flask-Admin's form
        validation pipeline, surfacing errors in the UI rather than as
        unhandled exceptions.
        """
        from sqlalchemy import inspect as sa_inspect

        if not is_created:
            # Use SQLAlchemy attribute history to detect whether state changed.
            history = sa_inspect(model).attrs.state.history
            if history.has_changes():
                # history.added holds the new value; it is empty only when the
                # attribute was explicitly cleared (set to None).  In that case
                # new_state is None, which is itself invalid and will be caught
                # by the check below.
                new_state = history.added[0] if history.added else None
                valid_states = {s for s, _ in _STATE_CHOICES}
                if new_state not in valid_states:
                    from wtforms import ValidationError
                    raise ValidationError(
                        f"Invalid state {new_state!r}. "
                        f"Choose one of: {', '.join(sorted(valid_states))}."
                    )
        else:
            # On create, validate state regardless (history is not yet tracked).
            valid_states = {s for s, _ in _STATE_CHOICES}
            if model.state not in valid_states:
                from wtforms import ValidationError
                raise ValidationError(
                    f"Invalid state {model.state!r}. "
                    f"Choose one of: {', '.join(sorted(valid_states))}."
                )

    def after_model_change(self, form, model, is_created: bool) -> None:
        """Called after a successful commit.

        Syncs the in-memory store (if the extension is available) so that
        both storage backends stay consistent.
        """
        if self._ext is not None:
            self._ext.update_state(model.session_id, model.state)

    # ------------------------------------------------------------------
    # Bulk actions
    # ------------------------------------------------------------------

    @action("refund", "Refund", "Mark selected payments as refunded?")
    def action_refund(self, ids: list[str]) -> None:
        """Mark the selected payment rows as *refunded*."""
        from flask import flash

        try:
            count = 0
            for pk in ids:
                record = self.get_one(pk)
                if record is not None:
                    record.state = "refunded"
                    if self._ext is not None:
                        self._ext.update_state(record.session_id, "refunded")
                    count += 1
            self.session.commit()
            flash(f"{count} payment(s) marked as refunded.", "success")
        except Exception as exc:  # noqa: BLE001
            self.session.rollback()
            flash(f"Failed to refund payments: {exc}", "danger")

    @action("cancel", "Cancel", "Cancel the selected payments?")
    def action_cancel(self, ids: list[str]) -> None:
        """Mark the selected payment rows as *cancelled*."""
        from flask import flash

        try:
            count = 0
            for pk in ids:
                record = self.get_one(pk)
                if record is not None:
                    record.state = "cancelled"
                    if self._ext is not None:
                        self._ext.update_state(record.session_id, "cancelled")
                    count += 1
            self.session.commit()
            flash(f"{count} payment(s) cancelled.", "success")
        except Exception as exc:  # noqa: BLE001
            self.session.rollback()
            flash(f"Failed to cancel payments: {exc}", "danger")

    @action("sync", "Sync from Provider", "Sync selected payments from the payment provider?")
    def action_sync(self, ids: list[str]) -> None:
        """Fetch live payment status from the provider and update each record."""
        from flask import flash

        if self._ext is None:
            flash("FlaskMerchants extension not configured; cannot sync.", "danger")
            return

        try:
            count = 0
            for pk in ids:
                record = self.get_one(pk)
                if record is None:
                    continue
                try:
                    status = self._ext.client.payments.get(record.session_id)
                    record.state = status.state.value
                    count += 1
                except Exception:  # noqa: BLE001
                    pass
            self.session.commit()
            flash(f"{count} payment(s) synced from provider.", "success")
        except Exception as exc:  # noqa: BLE001
            self.session.rollback()
            flash(f"Failed to sync payments: {exc}", "danger")
