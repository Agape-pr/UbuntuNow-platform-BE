# Ubuntunow Platform - Microservices Deployment on Railway

This guide outlines how to deploy the newly reorganized monorepo architecture for the **ubuntunow-platform** onto Railway.

## 1. Monorepo Setup in Railway
Railway natively supports Monorepos. Instead of deploying 7 different GitHub repositories, you will connect this single **`ubuntunow-platform`** repository to Railway and deploy 7 independent Services from it.

### Step-by-Step UI Deployment:
1. Go to your **Railway Dashboard**.
2. Click **New Project** -> **Deploy from GitHub repo**.
3. Select your `UbuntuNow-platform-BE` repository.
4. Railway will scan the Root directory and might fail at first because it sees multiple apps. 
5. In your project dashboard, click **+ New** -> **GitHub Repo** (Select the repo again) to add a second service. Do this for all 7 services.
6. For each service, go to **Settings -> Build**.
7. Change the **Builder** to `Dockerfile` instead of `Nixpacks/Railpack`.
8. Change the **Dockerfile Path** to reflect the specific service (e.g., `api-gateway/Dockerfile`, `auth-service/Dockerfile`, etc.).

**Important:** Do **NOT** change the "Root Directory". Leave it as `/`. The Dockerfiles have been specially written to pull everything from the root so they can access the shared folders!

## 2. Docker & Shared Utilities Build Support
The Dockerfiles for all 6 Python microservices have been fully customized to handle the monorepo context.

When Railway runs the Docker build from the Root (`/`), the Dockerfiles automatically compile their own specific `.txt` dependencies and then securely copy the `shared/` python utilities into the image. You do not need any custom build commands!

## 3. Database Isolation (Single PG, Multiple Schemas)
According to the latest optimizations, the platform shares **one PostgreSQL Database**, but each service reads from **its own unique Schema**. This allows data separation without the cost of running 6 separate database instances!

1. Provision **1 PostgreSQL Database** in your Railway Project Canvas (e.g., call it `ubuntunow-db`).
2. For **EVERY** Python Service, go to the **Variables** tab, and add the same Database connection string:
   - `DATABASE_URL` = `${{Postgres.DATABASE_URL}}`
3. Next, for **EACH** individual service, define its unique Schema via the `DB_SCHEMA` variable:
   - In `auth-service`: `DB_SCHEMA=auth_schema`
   - In `store-service`: `DB_SCHEMA=store_schema`
   - In `product-service`: `DB_SCHEMA=product_schema`
   - In `order-service`: `DB_SCHEMA=order_schema`
   - In `payment-service`: `DB_SCHEMA=payment_schema`
   - In `notification-service`: `DB_SCHEMA=notification_schema`

Upon deployment, each service will connect to the same PostgreSQL DB, but isolate its SQL tables entirely into its assigned `search_path` schema!

## 4. API Gateway Connection
The Node.js API Gateway acts as the unified reverse proxy. In the Gateway's **Variables** tab on Railway, define the internal Railway URLs to the Python microservices so that it knows where to route requests.

```env
AUTH_SERVICE_URL=http://auth-service.railway.internal:8000
STORE_SERVICE_URL=http://store-service.railway.internal:8000
PRODUCT_SERVICE_URL=http://product-service.railway.internal:8000
# ... etc ...
```
*(Railway provides a `<service-name>.railway.internal` network for services in the same project).*

By routing traffic to your **API Gateway's Public Domain**, your frontend will hit `/api/v1/auth`, which smoothly redirects internally to the isolated Auth Microservice!

## 5. Internal Service Token (required)
Internal service-to-service endpoints (`.../internal/...`) require a shared secret in the `X-Internal-Token` header. Set the **same** value as `INTERNAL_SERVICE_TOKEN` on **every** service (auth, store, product, order, payment, notification) — and in your local `.env` for docker-compose.

Generate one with: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`

If it is missing or differs between services, internal calls are rejected (fail closed): orders will not be marked paid after a payment, seller payouts cannot be released, and seller JWTs will lack `store_id`.

## 6. API Gateway Settings (optional variables)
Set these on the **API Gateway** service. All have safe defaults.

| Variable | Default | Purpose |
|---|---|---|
| `CORS_ALLOWED_ORIGINS` | `www.ubuntunow.rw`, `ubuntunow.rw`, `dev.ubuntunow.rw`, `admin.ubuntunow.rw`, `ubuntu-nexus-front.vercel.app`, localhost:3000/8080 | Comma-separated list of browser origins allowed to call the API. Setting it **replaces** the defaults, so include every frontend. |
| `EXPOSE_DOCS` | off | Set to `true` to serve `/api/docs`, `/api/schema`, `/api/redoc`. Leave off in production unless needed. |
| `RATE_LIMIT_AUTH` | `30` | Max login/register/OTP requests per IP per 15 min. |
| `RATE_LIMIT_GENERAL` | `1000` | Max other requests per IP per 15 min. Payment webhooks and `/health` are never limited. |
| `MAX_BODY_MB` | `25` | Max request body size. |

## 7. Admin portal (admin.ubuntunow.rw) — backend notes
- **Admin sign-in** is two-step: password, then a 6-digit code emailed to the admin (`/users/admin/login` → `/users/admin/login/verify`). The normal `/users/login` refuses admin accounts. Admin access tokens last 10 minutes, and the session 8 hours.
- **Permissions** (enforced on the server): `manage_users`, `manage_sellers`, `view_orders`, `manage_payments`, `view_audit_log`. Only super admins can create, edit or remove admins.
- **Payment-service needs `AUTH_SERVICE_URL`** (e.g. `http://auth-service.railway.internal:8000`) so payouts can be written to the audit log. Without it, payouts still work but are not recorded.
- **First super admin:** set `ADMIN_SETUP_SECRET` on auth-service, then `POST /api/v1/users/admin/setup/` with `{"email": "...", "secret": "..."}` for an existing registered account.
- All services must share the same `DJANGO_SECRET_KEY` (they verify each other's JWTs) and `INTERNAL_SERVICE_TOKEN`.

## 8. Runtime, security hardening and payment settings
- **Python 3.12 / Django 5.2 LTS.** The images moved from Python 3.9 and Django 4.2 (both past end of life). Builds
  install pinned versions from `constraints.txt`. Nothing to configure on Railway: it rebuilds from the Dockerfiles.
- **IntouchPay callback secret (recommended before live keys).** Set `INTOUCH_WEBHOOK_SECRET` on payment-service
  to a long random value. The callback URL given to IntouchPay then carries `?token=<secret>` and the webhook rejects
  anything without it. Until it is set the webhook still works, but logs a warning on every callback.
  Set it when no mobile-money payment is in flight, then run one sandbox payment to confirm the callback still arrives.
- **Removed:** the `mock-payment` order endpoint (it let any buyer mark their own order paid).
- **Payment status** is now only visible to the buyer who owns the order and to admins with `manage_payments`.
- **OTP endpoints** answer identically whether or not an email has an account, and send at most one code per minute.
- **Errors** returned to clients no longer include internal details; the details are in the service logs.
