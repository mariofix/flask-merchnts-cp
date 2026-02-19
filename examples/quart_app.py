"""Quart async app using flask-merchants with DummyProvider.

Requires the quart extra::

    pip install "flask-merchants[quart]"

Run with::

    python examples/quart_app.py

Then use the same endpoints as the Flask version:

    # JSON checkout
    curl -X POST http://localhost:5000/merchants/checkout \\
         -H "Content-Type: application/json" \\
         -d '{"amount": "9.99", "currency": "USD"}'

    # Payment status
    curl http://localhost:5000/merchants/status/SESSION_ID

    # Webhook
    curl -X POST http://localhost:5000/merchants/webhook \\
         -H "Content-Type: application/json" \\
         -d '{"payment_id": "SESSION_ID", "event_type": "payment.succeeded"}'
"""

from quart import Quart

from flask_merchants import FlaskMerchants

app = Quart(__name__)
app.config["MERCHANTS_URL_PREFIX"] = "/merchants"

# FlaskMerchants detects Quart and registers the async blueprint automatically
ext = FlaskMerchants(app)

if __name__ == "__main__":
    app.run(debug=True)
