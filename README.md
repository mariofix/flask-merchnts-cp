# flask-merchants

A Flask extension for the [merchants](https://github.com/mariofix/merchnts-cp) hosted-checkout payment SDK.

## Features

- Flask extension class (`FlaskMerchants`) with `init_app` support
- Blueprint with routes for checkout, success/cancel landing pages, payment status, and webhooks
- Uses `DummyProvider` by default – no credentials needed for local development
- Optional Flask-Admin views (under `flask_merchants.contrib.admin`) to list and update payment statuses

## Installation

```bash
pip install flask-merchants          # core
pip install "flask-merchants[admin]" # with Flask-Admin support
```

## Quick Start

```python
from flask import Flask
from flask_merchants import FlaskMerchants

app = Flask(__name__)
ext = FlaskMerchants(app)  # uses DummyProvider by default
```

### Available routes (default prefix `/merchants`)

| Method | Path | Description |
|--------|------|-------------|
| GET/POST | `/merchants/checkout` | Create a checkout session |
| GET | `/merchants/success` | Success landing page |
| GET | `/merchants/cancel` | Cancel landing page |
| GET | `/merchants/status/<payment_id>` | Live payment status |
| POST | `/merchants/webhook` | Receive webhook events |

### Configuration

| Key | Default | Description |
|-----|---------|-------------|
| `MERCHANTS_URL_PREFIX` | `/merchants` | URL prefix for the blueprint |
| `MERCHANTS_WEBHOOK_SECRET` | `None` | HMAC-SHA256 secret for webhook verification |

### Bring your own model

Install the `db` extra and mix :class:`~flask_merchants.models.PaymentMixin`
into your own SQLAlchemy model.  Pass it via `model=` to
:class:`~flask_merchants.FlaskMerchants`:

```python
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer
from flask_merchants import FlaskMerchants
from flask_merchants.models import PaymentMixin

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

class Pagos(PaymentMixin, db.Model):
    __tablename__ = "pagos"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # add your own columns here …

app = Flask(__name__)
ext = FlaskMerchants(app, db=db, model=Pagos)
```

From Flask-Admin you can then **Refund**, **Cancel**, and **Sync** payments:

```python
from flask_merchants.contrib.sqla import PaymentModelView
from flask_admin import Admin

admin = Admin(app)
admin.add_view(PaymentModelView(Pagos, db.session, ext=ext, name="Pagos"))
```

### Flask-Admin (optional)

```python
from flask_admin import Admin
from flask_merchants.contrib.admin import PaymentView

admin = Admin(app, name="My Shop")
admin.add_view(PaymentView(ext, name="Payments", endpoint="payments"))
```

## Examples

See the `examples/` directory:

- `examples/basic_app.py` – basic usage with DummyProvider
- `examples/admin_app.py` – usage with Flask-Admin (in-memory store)
- `examples/sqla_app.py` – SQLAlchemy-backed payments with Flask-Admin
- `examples/pagos_app.py` – **bring your own model** (`Pagos`) with Flask-Admin

## Tests

```bash
pip install "flask-merchants[dev]"
pytest
```

## License

MIT
