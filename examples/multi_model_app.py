"""Example: one FlaskMerchants instance, two payment models (Pagos + Paiements).

A single ``ext`` instance manages payments stored in two separate tables.
Each table is an independent SQLAlchemy model that uses ``PaymentMixin``.

Requires the db extra::

    pip install "flask-merchants[db]"

Run with::

    python examples/multi_model_app.py

Then:
  - Create a "pagos" checkout:     POST http://localhost:5000/merchants/checkout
    The blueprint saves to the *first* registered model (Pagos) by default.
  - Manage Pagos:     http://localhost:5000/admin/pagos/
  - Manage Paiements: http://localhost:5000/admin/paiements/

To direct a checkout to a specific model call ``ext.save_session()`` yourself
instead of relying on the blueprint's automatic save, for example::

    session = ext.client.payments.create_checkout(...)
    ext.save_session(session, model_class=Paiements)
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
# 1. Shared declarative base and two payment models.
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)


class Pagos(PaymentMixin, db.Model):
    """Spanish-market payments."""

    __tablename__ = "pagos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)


class Paiements(PaymentMixin, db.Model):
    """French-market payments."""

    __tablename__ = "paiements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)


# ---------------------------------------------------------------------------
# 2. Single FlaskMerchants instance that manages *both* models.
#    The blueprint's auto-save goes to Pagos (the first model).
#    Use ext.save_session(session, model_class=Paiements) to save explicitly.
# ---------------------------------------------------------------------------

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-me-in-production"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///multi_model.db"
app.config["MERCHANTS_URL_PREFIX"] = "/merchants"

ext = FlaskMerchants(app, db=db, models=[Pagos, Paiements])
db.init_app(app)

# ---------------------------------------------------------------------------
# 3. Flask-Admin: one view per model, both connected to the same ext.
# ---------------------------------------------------------------------------

admin = Admin(app, name="Multi-Model Admin")
admin.add_view(
    PaymentModelView(Pagos, db.session, ext=ext, name="Pagos", endpoint="pagos")
)
admin.add_view(
    PaymentModelView(Paiements, db.session, ext=ext, name="Paiements", endpoint="paiements")
)

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True)
