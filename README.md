# flask-merchants

A Flask/Quart extension for the [merchants](https://github.com/mariofix/merchnts-cp) hosted-checkout payment SDK.

## Features

- Flask/Quart extension class (`FlaskMerchants`) with `init_app` support
- Blueprint with routes for checkout, success/cancel landing pages, payment status, and webhooks
- Uses `DummyProvider` by default – no credentials needed for local development
- Optional Flask-Admin views (under `flask_merchants.contrib.admin`) to list and update payment statuses
- Optional SQLAlchemy-backed Flask-Admin view (`flask_merchants.contrib.sqla`) with bulk refund/cancel/sync actions
- Quart (async) support – async blueprint selected automatically when a `quart.Quart` app is detected

## Installation

```bash
pip install flask-merchants           # core
pip install "flask-merchants[admin]"  # with Flask-Admin support
pip install "flask-merchants[db]"     # with SQLAlchemy + Flask-Admin support
pip install "flask-merchants[quart]"  # with Quart (async) support
```

## Quick Start

```python
from flask import Flask
from flask_merchants import FlaskMerchants

app = Flask(__name__)
ext = FlaskMerchants(app)  # uses DummyProvider by default
```

### Quart (async)

`FlaskMerchants` detects a `quart.Quart` application automatically and registers
an async blueprint instead:

```python
from quart import Quart
from flask_merchants import FlaskMerchants

app = Quart(__name__)
ext = FlaskMerchants(app)   # async blueprint selected automatically
```

Requires the `quart` extra:

```bash
pip install "flask-merchants[quart]"
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

Install the `db` extra and mix `PaymentMixin` into your own SQLAlchemy model.
Pass it via `model=` to `FlaskMerchants`:

```python
from flask import Flask
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

### Multiple payment models in the same app

A **single** `FlaskMerchants` instance can manage any number of models at once
using `models=`:

```python
class Pagos(PaymentMixin, db.Model):
    __tablename__ = "pagos"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

class Paiements(PaymentMixin, db.Model):
    __tablename__ = "paiements"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

ext = FlaskMerchants(app, db=db, models=[Pagos, Paiements])

# Direct a checkout to a specific model:
session = ext.client.payments.create_checkout(...)
ext.save_session(session, model_class=Paiements)

# get_session / update_state / refund_session / cancel_session all search
# across every registered model automatically.

# all_sessions() returns every record from all models combined.
# all_sessions(model_class=Pagos) filters to a single model.
```

Add a separate Flask-Admin view for each model, all backed by the same `ext`:

```python
from flask_merchants.contrib.sqla import PaymentModelView
from flask_admin import Admin

admin = Admin(app)
admin.add_view(PaymentModelView(Pagos,     db.session, ext=ext, name="Pagos",     endpoint="pagos"))
admin.add_view(PaymentModelView(Paiements, db.session, ext=ext, name="Paiements", endpoint="paiements"))
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
- `examples/multi_model_app.py` – **multiple models** (`Pagos` + `Paiements`) with one `ext`
- `examples/quart_app.py` – Quart (async) usage with DummyProvider

## Tests

```bash
pip install "flask-merchants[dev]"
pytest
```

## License

MIT
