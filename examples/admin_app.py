"""Flask app with Flask-Admin to manage payment statuses.

Requires the admin extra::

    pip install "flask-merchants[admin]"

Run with::

    python examples/admin_app.py

Then open http://localhost:5000/admin/payments/ to manage stored payments.
Create a checkout first at http://localhost:5000/merchants/checkout.
"""

from flask import Flask
from flask_admin import Admin
from flask_merchants import FlaskMerchants
from flask_merchants.contrib.admin import PaymentView

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-me-in-production"
app.config["MERCHANTS_URL_PREFIX"] = "/merchants"

ext = FlaskMerchants(app)

admin = Admin(app, name="Payment Admin")
admin.add_view(PaymentView(ext, name="Payments", endpoint="payments"))

if __name__ == "__main__":
    app.run(debug=True)
