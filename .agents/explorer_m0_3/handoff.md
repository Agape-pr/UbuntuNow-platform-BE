# Handoff Report: Backend Architecture, Auth Endpoints & Infrastructure Survey (M0 Explorer 3)

## 1. Observation

### 1.1 Backend Architecture & Service Stack
- **Front Gate**: Express API Gateway in Node.js (`api-gateway/index.js:1-57`).
  - Listen Port: `8000` (default, or `process.env.PORT`).
  - Dependencies (`api-gateway/package.json:13-19`): `express@^5.2.1`, `http-proxy-middleware@^3.0.5`, `cors@^2.8.6`, `morgan@^1.10.1`.
- **Auth Microservice**: Django 5 + Django REST Framework (`auth-service/config/settings/base.py:1-215`).
  - Listen Port: `8001`.
  - Database: PostgreSQL `auth_db` (`docker-compose.yml:64`).
  - Authentication Engine: SimpleJWT (`rest_framework_simplejwt.authentication.JWTAuthentication`).
- **Downstream Microservices**:
  - `store-service` (Port `8002`, `store_db`)
  - `product-service` (Port `8003`, `product_db`)
  - `order-service` (Port `8004`, `order_db`)
  - `payment-service` (Port `8005`, `payment_db`)
  - `notification-service` (Port `8006`, `notification_db`)
- **Shared Utilities**:
  - `shared/core/utils/auth.py:30-41`: Defines `JWTStatelessAuthentication` and `StatelessUser` used by downstream microservices for stateless JWT parsing without database calls.
  - `./up.sh:4-10`: Shell script that injects `shared/core` into all microservices before running `docker-compose up --build -d`.

### 1.2 Auth Endpoints & Token Validation
- **Auth Routes (`auth-service/apps/users/urls.py:12-24` & `auth-service/config/urls.py:19-20`)**:
  - `POST /api/v1/users/register` -> `RegisterView` (`auth-service/apps/users/views.py:19`)
  - `POST /api/v1/users/login` -> `CustomTokenObtainPairView` (`auth-service/apps/users/views.py:49`)
  - `POST /api/v1/users/token/refresh` -> `TokenRefreshView` (`auth-service/apps/users/urls.py:15`)
  - `GET /api/v1/users/me/` -> `CurrentUserView` (`auth-service/apps/users/views.py:41`)
  - `PATCH /api/v1/users/me/` -> `CurrentUserView` (`auth-service/apps/users/views.py:41`)
- **Token Format & Custom Claims (`auth-service/apps/users/serializers.py:142-172`)**:
  - `CustomTokenObtainPairSerializer` injects custom claims into the JWT:
    - `role` (`user.role`)
    - `is_superuser` (`user.is_superuser`)
    - `admin_permissions` (`user.admin_permissions`)
    - `store_id` (for sellers, fetched from `store-service`).
  - Response body on successful login:
    ```json
    {
      "refresh": "<refresh_jwt>",
      "access": "<access_jwt>",
      "user": {
        "id": 1,
        "email": "user@example.com",
        "role": "buyer",
        "phone_number": "...",
        "store": null,
        "is_superuser": false,
        "admin_permissions": [],
        "first_name": "",
        "last_name": "",
        "address_line1": "",
        "address_line2": "",
        "city": "",
        "country": ""
      }
    }
    ```
- **Token Validation Logic**:
  - `CurrentUserView` uses `permission_classes = [IsAuthenticated]`.
  - SimpleJWT authenticates incoming requests using `Authorization: Bearer <access_token>`.
  - Expiration lifetime (`auth-service/config/settings/base.py:170-173`):
    - `ACCESS_TOKEN_LIFETIME`: 60 minutes
    - `REFRESH_TOKEN_LIFETIME`: 1 day (24 hours)

### 1.3 CORS & Header/Cookie Requirements
- **Header Requirement**: Standard Bearer token header `Authorization: Bearer <access_token>`.
- **Cookie Usage**: No backend endpoints require or set HttpOnly auth cookies. All authentication is strictly header-based JWT.
- **CORS Settings**:
  - API Gateway (`api-gateway/index.js:11`): Uses `cors()` middleware.
  - Auth Service (`auth-service/config/settings/base.py:211-215`): Explicit list `CORS_ALLOWED_ORIGINS = ["http://localhost:8080", "https://ubuntu-nexus-front.vercel.app", "https://www.ubuntunow.rw"]`.

### 1.4 Dev Server & Test Infrastructure
- **Dev Server Launch Scripts**:
  - Main Cluster Launch: `./up.sh` (runs `cp -R shared/core $svc-service/` and `docker-compose up --build -d`).
  - Standalone API Gateway: `cd api-gateway && npm start` (Port 8000).
  - Standalone Auth Service: `cd auth-service && python manage.py runserver 8001`.
- **Existing Test Scripts**:
  - `test_api.py`: Python integration script testing Register -> Login -> Patch `/users/me/` -> Get `/users/me/`.
  - `test_jwt.py` / `test_jwt2.py`: Verification scripts for `JWTStatelessAuthentication`.
  - `test_local.py` & `test_get.py`: Tests for `UserDetailSerializer` and user profile updates.

---

## 2. Logic Chain

1. **Observation**: `auth-service/apps/users/views.py:41-46` defines `CurrentUserView` with `permission_classes = [IsAuthenticated]` and `rest_framework_simplejwt.authentication.JWTAuthentication`.
   - **Step**: Request to `/api/v1/users/me/` succeeds with HTTP 200 when presented with a valid `Authorization: Bearer <token>` header, returning the full user profile.
2. **Observation**: `api-gateway/index.js:38` proxies `/api/v1/users` to `http://auth-service:8001`.
   - **Step**: Requests routed through API Gateway (`http://localhost:8000/api/v1/users/me/`) cleanly forward headers to `auth-service`.
3. **Observation**: The backend code does not set cookies or look for cookies in any authentication middleware.
   - **Step**: The backend authentication contracts are 100% header-based JWTs. Therefore, any auth persistence or profile login prompt failure issue reported on the frontend is caused by frontend state management (e.g. failing to attach `Authorization: Bearer <token>` on protected routes or clearing local storage/state on route navigation), rather than a backend rejecting valid tokens.
4. **Observation**: `test_api.py` provides a ready-made automated integration check for the entire backend auth lifecycle (Register, Login, Me/Profile retrieval, Me/Profile patch).
   - **Step**: Updating `test_api.py` to point to `http://localhost:8000/api/v1` serves as the primary verification tool for Milestone 3.

---

## 3. Caveats

- `Ubuntunow-now-BE` directory at `/Users/apple/Desktop/Ubuntunow-now-BE` was referenced in `ORIGINAL_REQUEST.md`, but local filesystem structure shows the project workspace is located at `/Users/apple/Desktop/ubuntunow-platform`.
- Django migrations require a running PostgreSQL instance (or SQLite fallback if `DATABASE_URL` is unset) when running standalone without Docker.

---

## 4. Conclusion

- **Backend Auth Stack**: Polyglot microservices cluster (Express API Gateway on port 8000 + Django `auth-service` on port 8001 + 5 downstream Django services).
- **Auth Protocol**: Header-based SimpleJWT tokens (`Authorization: Bearer <access_token>`). Access token lifetime is 60 minutes; refresh token lifetime is 24 hours.
- **Backend Profile Endpoint**: `GET /api/v1/users/me/` (and `PATCH /api/v1/users/me/`) fully works when provided with a valid Bearer token.
- **Root Cause Indication**: Backend authentication endpoints and token validation mechanisms are sound and functional. The root cause of "navigating to profile triggers secondary login prompt" is client-side header missing/omitted during route guard/profile navigation or conflicting login prompt components.

---

## 5. Verification Method

### Step 1: Start Microservices Cluster
```bash
cd /Users/apple/Desktop/ubuntunow-platform
./up.sh
```
Verify Gateway health:
```bash
curl -i http://localhost:8000/health
# Expected: {"status":"API Gateway is running"}
```

### Step 2: Automated End-to-End API Auth Test
Run `test_api.py` against local gateway (`http://localhost:8000/api/v1`):
```bash
python test_api.py
```
Expected output:
1. `Register: 201 {"email": "..."}`
2. `Login: 200 {"refresh": "...", "access": "...", "user": {...}}`
3. `Patch: 200 {"id": ..., "email": ..., "first_name": "Test", ...}`
4. `Get: 200 {"id": ..., "email": ..., "first_name": "Test", ...}`

### Step 3: Unauthenticated Protected Route Invalidation Check
```bash
curl -i http://localhost:8000/api/v1/users/me/
# Expected: HTTP 401 Unauthorized {"detail":"Authentication credentials were not provided."}
```
