"""Basic Flask app using flask-merchants with DummyProvider.

Run with::

    python examples/basic_app.py

Then open http://localhost:5000/merchants/checkout in your browser or use curl:

    # Redirect to checkout
    curl -L http://localhost:5000/merchants/checkout

    # JSON response (returns session_id and redirect_url)
    curl -X POST http://localhost:5000/merchants/checkout \\
         -H "Content-Type: application/json" \\
         -d '{"amount": "49.99", "currency": "USD"}'

    # Get payment status (replace SESSION_ID with a real one)
    curl http://localhost:5000/merchants/status/SESSION_ID

    # Send a simulated webhook event
    curl -X POST http://localhost:5000/merchants/webhook \\
         -H "Content-Type: application/json" \\
         -d '{"payment_id": "SESSION_ID", "event_type": "payment.succeeded"}'
"""

from flask import Flask
from flask_merchants import FlaskMerchants

app = Flask(__name__)
app.config["MERCHANTS_URL_PREFIX"] = "/merchants"

# DummyProvider is used by default – no credentials needed
ext = FlaskMerchants(app)

if __name__ == "__main__":
    app.run(debug=True)
