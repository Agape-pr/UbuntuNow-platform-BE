# Ubuntunow Platform - Microservices Deployment on Railway

This guide outlines how to deploy the newly reorganized monorepo architecture for the **ubuntunow-platform** onto Railway.

## 1. Monorepo Setup in Railway
Railway natively supports Monorepos. Instead of deploying 7 different GitHub repositories, you will connect this single **`ubuntunow-platform`** repository to Railway and deploy 7 independent Services from it.

### Step-by-Step UI Deployment:
1. Go to your **Railway Dashboard**.
2. Click **New Project** -> **Deploy from GitHub repo**.
3. Select your `ubuntunow-platform` repository.
4. Railway will scan the Root directory. Since nothing is there except folders, you need to configure each service manually.
5. In your project dashboard, click **+ New** -> **GitHub Repo** (Select the repo again).
6. Once added, click the newly created service, go to **Settings** -> **Root Directory**, and type `api-gateway/`. 
7. Rename the Railway Service to **API Gateway**.

Repeat Step 5-7 for all the corresponding Python microservices, setting their **Root Directories** to:
- `auth-service/`
- `store-service/`
- `product-service/`
- `order-service/`
- `payment-service/`
- `notification-service/`

## 2. Docker & Shared Utilities Build Support
Because the prompt strictly specified that **no business logic or imports should be modified**, the Python microservices internally expect the `core/` utilities to be sitting next to `manage.py` and `config/` (or available in the PYTHONPATH).

Because Docker cannot access folders *outside* of its build context (i.e. `auth-service/` cannot read `../shared/`), you must inject the `shared/` resources into each service right before Docker builds them.

### Railway Custom Build Command Fix
To easily solve this on Railway without altering Dockerfiles, go to the **Settings** tab of **each Python Service** on your Railway dashboard, scroll down to **Build Command**, and enter the following overriding sequence:

```bash
cp -r ../shared/core/ ./core/ && docker build -t app:latest .
```
*(Alternatively, simply place a copy of the `core` folder physically inside each microservice folder in your GitHub repository and let Railway build it natively).*

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
