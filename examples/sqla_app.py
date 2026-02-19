"""Flask app with SQLAlchemy-backed payments and Flask-Admin ModelView.

Requires the db extra::

    pip install "flask-merchants[db]"

Run with::

    python examples/sqla_app.py

Then:
  - Create a checkout: http://localhost:5000/merchants/checkout
  - Manage payments: http://localhost:5000/admin/payment/
"""

from flask import Flask
from flask_admin import Admin
from flask_sqlalchemy import SQLAlchemy

from flask_merchants import FlaskMerchants
from flask_merchants.contrib.sqla import PaymentModelView
from flask_merchants.models import Base, Payment

db = SQLAlchemy(model_class=Base)

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-me-in-production"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///payments.db"
app.config["MERCHANTS_URL_PREFIX"] = "/merchants"

ext = FlaskMerchants(app, db=db)
db.init_app(app)

admin = Admin(app, name="Payment Admin")
admin.add_view(
    PaymentModelView(Payment, db.session, ext=ext, name="Payments")
)

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True)
