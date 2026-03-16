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
