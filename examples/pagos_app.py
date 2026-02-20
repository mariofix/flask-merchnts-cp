"""Example: bring-your-own SQLAlchemy model with Flask-Admin.

This example shows how a developer can define their own SQLAlchemy model
(``Pagos``) and plug it straight into flask-merchants so that payments are
stored in *their* table, fully manageable from Flask-Admin.

Requires the db extra::

    pip install "flask-merchants[db]"

Run with::

    python examples/pagos_app.py

Then:
  - Create a checkout: http://localhost:5000/merchants/checkout
  - Manage pagos (payments): http://localhost:5000/admin/pagos/

The admin view exposes Refund, Cancel, and Sync-from-Provider bulk actions.
"""

from flask import Flask
from flask_admin import Admin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from flask_merchants import FlaskMerchants
from flask_merchants.contrib.sqla import PaymentModelView
from flask_merchants.models import PaymentMixin


# ---------------------------------------------------------------------------
# 1. Define your own declarative base and model.
#    Mix in PaymentMixin to get all the payment fields and helpers.
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)


class Pagos(PaymentMixin, db.Model):
    """Application-level payment model.

    Using PaymentMixin gives us all the columns and helpers that
    flask-merchants needs (session_id, state, to_dict, …).  We can also
    add our own application-specific columns here.
    """

    __tablename__ = "pagos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)


# ---------------------------------------------------------------------------
# 2. Wire everything together.
#    Pass models=[Pagos] so FlaskMerchants stores payments in the pagos table.
# ---------------------------------------------------------------------------

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-me-in-production"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///pagos.db"
app.config["MERCHANTS_URL_PREFIX"] = "/merchants"

# DummyProvider is used by default – no credentials needed for local dev.
ext = FlaskMerchants(app, db=db, models=[Pagos])
db.init_app(app)

# ---------------------------------------------------------------------------
# 3. Add Flask-Admin to manage Pagos records.
#    PaymentModelView provides Refund, Cancel, and Sync bulk actions.
# ---------------------------------------------------------------------------

admin = Admin(app, name="Pagos Admin")
admin.add_view(
    PaymentModelView(Pagos, db.session, ext=ext, name="Pagos", endpoint="pagos")
)

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True)
