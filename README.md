# UbuntuNow platform — backend

Social-commerce marketplace for Rwanda: sellers get storefronts, buyers pay through escrow
(Pesapal cards, MTN MoMo / Airtel Money via IntouchPay) and admins release payouts.

## Architecture

```
browser ──► api-gateway (Node/Express) ──► auth-service          users, sign-in, OTP, admin API, audit log
                                       ├─► store-service         seller stores, payout numbers
                                       ├─► product-service       catalogue, stock
                                       ├─► order-service         checkout, order lifecycle
                                       ├─► payment-service       payments, webhooks, escrow release
                                       └─► notification-service  in-app notifications (RabbitMQ consumer)
```

- Each service is a Django REST app with its own PostgreSQL database; they talk over HTTP and RabbitMQ.
- `shared/core` is code used by every service (stateless JWT auth, admin permissions, internal service
  token, audit client, RabbitMQ helpers). Docker images copy it to `/shared`; import it as `shared.core...`.
- Services never trust the public internet for each other's endpoints: `/internal/` routes are blocked at the
  gateway **and** require the `X-Internal-Token` header (`INTERNAL_SERVICE_TOKEN`).
- Admin accounts sign in with password + emailed code and get short-lived tokens; permissions are enforced
  on the server (`shared/core/utils/admin_permissions.py`).

## Run it locally

```bash
cp .env.example .env        # then fill in the values (see railway-deployment.md for the full list)
docker compose up --build   # gateway on http://localhost:8000
```

Without Docker, per service: `python3.12 -m venv venv && venv/bin/pip install -r <service>/requirements.txt -c constraints.txt`,
then `cd <service> && python manage.py migrate && python manage.py runserver`.

## Tests

```bash
cd auth-service && python manage.py test        # likewise store-, product-, order-, payment-, notification-service
cd api-gateway && npm ci && npm test
```

CI (`.github/workflows/ci.yml`) runs all of them on Python 3.12 against PostgreSQL 16, checks for missing
migrations, and audits dependencies.

## Dependencies

Each service lists only its direct dependencies in `requirements.txt`. **Exact versions of everything**
(including transitive packages) live in `constraints.txt`, which every install uses (`-c constraints.txt`) so
builds are reproducible. To upgrade, install the new versions into a clean Python 3.12 virtualenv, run every
test suite, then regenerate the file with `pip freeze` (keep the header comment).

## Deploying

See [railway-deployment.md](railway-deployment.md): environment variables, service URLs, the admin portal and
the payment-provider settings.
