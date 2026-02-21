# flask-merchants

A Flask/Quart extension for the [merchants](https://github.com/mariofix/merchnts-cp) hosted-checkout payment SDK.

## Features

- Flask/Quart extension class (`FlaskMerchants`) with full `init_app` support – pass `db`, `models`, `provider`, `providers`, and `admin` either at construction time or deferred to `init_app` (application-factory friendly)
- Blueprint with routes for checkout, success/cancel landing pages, payment status, webhooks, and provider listing
- Multiple payment-provider support – register providers by name via the `merchants` SDK registry and select one per checkout request
- Uses `DummyProvider` by default – no credentials needed for local development
- Optional Flask-Admin views (under `flask_merchants.contrib.admin`) to list and update payment statuses
- **Automatic Flask-Admin integration** – pass `admin=` to `FlaskMerchants` to auto-register `PaymentView` and `ProvidersView` under the *Merchants* admin category with a single line
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
| GET | `/merchants/providers` | List available payment providers |
| GET | `/merchants/success` | Success landing page |
| GET | `/merchants/cancel` | Cancel landing page |
| GET | `/merchants/status/<payment_id>` | Live payment status |
| POST | `/merchants/webhook` | Receive webhook events |

### Configuration

| Key | Default | Description |
|-----|---------|-------------|
| `MERCHANTS_URL_PREFIX` | `/merchants` | URL prefix for the blueprint |
| `MERCHANTS_WEBHOOK_SECRET` | `None` | HMAC-SHA256 secret for webhook verification |

### Application factory pattern

All configuration parameters (`db`, `models`, `provider`, `providers`, `admin`) can be
passed either to `FlaskMerchants()` at construction time **or** to `init_app()`
later – whichever fits your project layout.  Both styles are equivalent:

```python
# Style A – everything up front
from flask import Flask
from flask_merchants import FlaskMerchants

app = Flask(__name__)
ext = FlaskMerchants(app, db=db, models=[Pagos])
```

```python
# Style B – config deferred to init_app (application-factory pattern)
# extensions.py
from flask_merchants import FlaskMerchants
merchants_ext = FlaskMerchants()

# app_factory.py
def create_app():
    app = Flask(__name__)
    db = SQLAlchemy(model_class=Base)
    merchants_ext.init_app(app, db=db, models=[Pagos], provider=MyProvider())
    return app
```

Parameters supplied to `init_app` override any value previously set in `__init__`.

### Flask-Admin integration (automatic)

Pass a `flask_admin.Admin` instance to `FlaskMerchants` and both admin views are
registered automatically under the **Merchants** category – no manual wiring needed:

```python
from flask import Flask
from flask_admin import Admin
from flask_merchants import FlaskMerchants

app = Flask(__name__)
admin = Admin(app, name="My Shop")
ext = FlaskMerchants(app, admin=admin)
# Done — PaymentView and ProvidersView registered under "Merchants"
```

Works with the application-factory pattern too:

```python
ext = FlaskMerchants()
ext.init_app(app, admin=admin)
```

Two views are registered automatically:

| View | URL | Description |
|------|-----|-------------|
| **Payments** | `/admin/merchants_payments/` | List, update, refund, cancel, and sync all stored payments |
| **Providers** | `/admin/merchants_providers/` | Debug view for every registered provider |

The **Providers** view shows the following information for each provider:

| Column | Description |
|--------|-------------|
| Provider Key | Unique key string (e.g. `dummy`, `stripe`) |
| Base URL | Provider API base URL |
| Auth Type | Auth strategy class (`None`, `ApiKeyAuth`, `TokenAuth`) |
| Auth Header | HTTP header the credential is sent in |
| Auth Value | Masked credential – first 5 chars + `…` + last 1 char (e.g. `sk_te…0`) |
| Transport | Transport layer class (e.g. `RequestsTransport`) |
| Payments | Number of stored payments routed to this provider |

You can also register the views manually when you need finer control:

```python
from flask_merchants.contrib.admin import register_admin_views

register_admin_views(admin, ext)
```

Or add individual views directly:

```python
from flask_merchants.contrib.admin import PaymentView, ProvidersView

admin.add_view(PaymentView(ext, name="Payments", endpoint="payments", category="Merchants"))
admin.add_view(ProvidersView(ext, name="Providers", endpoint="providers", category="Merchants"))
```

### Payment provider selection

Register one or more providers via the `merchants` SDK registry, then select
one per checkout request using the `provider` field:

```python
import merchants
from merchants.providers.dummy import DummyProvider

merchants.register_provider(DummyProvider())
# merchants.register_provider(StripeProvider(api_key="sk_test_..."))

app = Flask(__name__)
ext = FlaskMerchants(app)
```

You can also pass providers directly through the extension:

```python
ext = FlaskMerchants(app, provider=DummyProvider())
# or a list:
ext = FlaskMerchants(app, providers=[DummyProvider(), StripeProvider(api_key="sk_test_...")])
```

List available providers at runtime:

```
GET /merchants/providers
→ {"providers": ["dummy", "stripe"]}
```

Select a provider at checkout:

```
POST /merchants/checkout
{"amount": "19.99", "currency": "USD", "provider": "stripe"}
```

If `provider` is omitted the first registered provider is used.  An unknown
provider key returns HTTP 400.

### Bring your own model

Install the `db` extra and mix `PaymentMixin` into your own SQLAlchemy model.
Pass it via `models=` to `FlaskMerchants`:

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
ext = FlaskMerchants(app, db=db, models=[Pagos])
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

### Flask-Admin (legacy / manual)

For fine-grained control, or when using the SQLAlchemy-backed view, you can still
register individual views manually:

```python
from flask_admin import Admin
from flask_merchants.contrib.admin import PaymentView

admin = Admin(app, name="My Shop")
admin.add_view(PaymentView(ext, name="Payments", endpoint="payments"))
```

See the [Flask-Admin integration (automatic)](#flask-admin-integration-automatic) section
above for the recommended single-line approach.

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
