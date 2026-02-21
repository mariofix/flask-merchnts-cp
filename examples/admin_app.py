"""Flask app with Flask-Admin to manage payment statuses.

Requires the admin extra::

    pip install "flask-merchants[admin]"

Run with::

    python examples/admin_app.py

Then open http://localhost:5000/admin/merchants_payments/ to manage stored payments
or http://localhost:5000/admin/merchants_providers/ to view registered providers.
Create a checkout first at http://localhost:5000/merchants/checkout.
"""

from flask import Flask
from flask_admin import Admin
from flask_merchants import FlaskMerchants

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-me-in-production"
app.config["MERCHANTS_URL_PREFIX"] = "/merchants"

admin = Admin(app, name="Payment Admin")
# Passing admin= automatically registers PaymentView and ProvidersView
# under category="Merchants" in the admin panel.
ext = FlaskMerchants(app, admin=admin)

if __name__ == "__main__":
    app.run(debug=True)
