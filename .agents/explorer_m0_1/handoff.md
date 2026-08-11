# Handoff Report: Survey & Architecture Mapping for Auth Persistence & Profile Flow

## 1. Observation

### Codebase Architecture & File Locations
The repository at `/Users/apple/Desktop/ubuntunow-platform` is a microservices backend platform containing the API gateway and core microservices. The frontend client (e.g. `ubuntu-nexus-front`) is decoupled and interfaces with this backend via the API Gateway.

Key files involved in authentication, session verification, and profile endpoints:

1. **API Gateway Routing & Proxy Interceptors**:
   - Path: `/Users/apple/Desktop/ubuntunow-platform/api-gateway/index.js`
   - Express proxy configuration using `http-proxy-middleware`. Forwarding rules:
     ```js
     app.use(proxy('/api/v1/auth', services.auth));
     app.use(proxy('/api/v1/users/store', services.store));
     app.use(proxy('/api/v1/store', services.store));
     app.use(proxy('/api/v1/users', services.auth));
     ```

2. **Auth Service Routes & Endpoints**:
   - Path: `/Users/apple/Desktop/ubuntunow-platform/auth-service/apps/users/urls.py`
     - Line 14: `path('login', CustomTokenObtainPairView.as_view(), name='token_obtain_pair')` -> `/api/v1/users/login`
     - Line 15: `path('token/refresh', TokenRefreshView.as_view(), name='token_refresh')` -> `/api/v1/users/token/refresh`
     - Line 16: `path('me/', CurrentUserView.as_view(), name='user-me')` -> `/api/v1/users/me/`
   - Path: `/Users/apple/Desktop/ubuntunow-platform/auth-service/config/urls.py`
     - Line 20: `path("api/v1/users/", include("apps.users.urls"))`

3. **Auth Service Views & Serializers**:
   - Path: `/Users/apple/Desktop/ubuntunow-platform/auth-service/apps/users/views.py`
     - Lines 41-46: `CurrentUserView` (RetrieveUpdateAPIView with `permission_classes = [IsAuthenticated]`) returns `self.request.user`.
     - Lines 49-51: `CustomTokenObtainPairView` returns JWT tokens.
   - Path: `/Users/apple/Desktop/ubuntunow-platform/auth-service/apps/users/serializers.py`
     - Lines 142-171: `CustomTokenObtainPairSerializer` generates JWT access and refresh tokens and appends `user` payload:
       ```json
       {
         "access": "<JWT_ACCESS_TOKEN>",
         "refresh": "<JWT_REFRESH_TOKEN>",
         "user": {
           "id": 1,
           "email": "user@example.com",
           "role": "buyer",
           "first_name": "...",
           "last_name": "...",
           "address_line1": "..."
         }
       }
       ```
     - Lines 97-122: `UserDetailSerializer` maps user profile details (`first_name`, `last_name`, `address_line1`, `address_line2`, `city`, `country`).

4. **Authentication Class & Middleware**:
   - Path: `/Users/apple/Desktop/ubuntunow-platform/shared/core/utils/auth.py` & `/Users/apple/Desktop/ubuntunow-platform/auth-service/core/utils/auth.py`
     - `JWTStatelessAuthentication` (inherits from `JWTAuthentication`) parses `Authorization: Bearer <token>` headers across microservices.
   - Path: `/Users/apple/Desktop/ubuntunow-platform/auth-service/config/settings/base.py`
     - Lines 154-157: `REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES'] = ('rest_framework_simplejwt.authentication.JWTAuthentication',)`
     - Lines 170-173: `SIMPLE_JWT = {'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60), 'REFRESH_TOKEN_LIFETIME': timedelta(days=1)}`
     - Lines 211-215: Hardcoded `CORS_ALLOWED_ORIGINS`:
       ```python
       CORS_ALLOWED_ORIGINS = [
           "http://localhost:8080",
           "https://ubuntu-nexus-front.vercel.app",
           "https://www.ubuntunow.rw",
       ]
       ```

---

## 2. Logic Chain

From observations of the codebase:

1. **Authentication Credentials Flow**:
   - **Login**: Frontend sends `POST /api/v1/users/login` with credentials. Backend returns JSON containing `access` token, `refresh` token, and `user` object.
   - **Storage**: Frontend client stores `access` and `refresh` tokens (in `localStorage`, `sessionStorage`, or cookies).
   - **Consumption**: Frontend sends `Authorization: Bearer <access_token>` in HTTP request headers to protected endpoints such as `/api/v1/users/me/`.

2. **Root Causes of Auth Persistence Failure & Conflicting Login Prompts**:
   - **Cause 1: Trailing Slash Redirection (`/api/v1/users/me` vs `/api/v1/users/me/`)**:
     - `auth-service/apps/users/urls.py` specifies `path('me/', ...)`.
     - When frontend clients or API callers request `/api/v1/users/me` (without a trailing slash), Django issues an HTTP `301 Moved Permanently` redirect to `/api/v1/users/me/`.
     - Standard HTTP client libraries and browser `fetch` implementations drop the `Authorization` header upon cross-origin redirects, or fail preflight checks on the redirected path. This results in an unauthenticated `401 Unauthorized` response, triggering the frontend router/guard to redirect users to a login prompt.
   - **Cause 2: Hardcoded CORS Origin Restrictions**:
     - In `auth-service/config/settings/base.py` (and `product-service/config/settings/base.py`), `CORS_ALLOWED_ORIGINS` is hardcoded at the bottom of the file to specific URLs (`localhost:8080`, `ubuntu-nexus-front.vercel.app`, `www.ubuntunow.rw`), overriding dynamic environment settings.
     - When running local dev servers on alternative ports (e.g. `localhost:3000`, `localhost:5173`, `localhost:8000`), CORS preflight checks (`OPTIONS`) fail for protected endpoints, preventing `Authorization` headers from being sent and throwing CORS errors that frontends interpret as session expiration.
   - **Cause 3: Lack of Trailing Slash Tolerances in DRF Routing**:
     - Requests to `/api/v1/users/me` vs `/api/v1/users/me/` should both be matched seamlessly without forcing 301 redirects that strip headers.

---

## 3. Caveats

- The frontend SPA client source code is hosted separately (deployed at `https://ubuntu-nexus-front.vercel.app` or running locally on frontend dev servers).
- Investigation was strictly read-only on `/Users/apple/Desktop/ubuntunow-platform`.

---

## 4. Conclusion

The authentication failure when navigating to profile (`/profile` / `/api/v1/users/me`) is caused by:
1. **Trailing Slash Header Drop on Redirect**: `auth-service/apps/users/urls.py` enforces `me/` with a trailing slash. Non-slashed requests `/api/v1/users/me` trigger a HTTP 301 redirect which strips the `Authorization: Bearer <token>` header.
2. **CORS Configuration Blockage**: Hardcoded `CORS_ALLOWED_ORIGINS` in `base.py` blocks frontend requests from non-whitelisted local ports (like `localhost:3000` or `localhost:5173`).

### Recommended Fix Strategy (for M1 & M2):
1. **Support slash and non-slash endpoints**: Update `auth-service/apps/users/urls.py` to allow both `me` and `me/` (or set `APPEND_SLASH = False` / add optional trailing slash matching in URL patterns).
2. **Make CORS configurable via environment variables**: Fix `CORS_ALLOWED_ORIGINS` in `auth-service/config/settings/base.py` (and all microservice base settings) so it reads from `CORS_ALLOWED_ORIGINS` env var or permits `CORS_ALLOW_ALL_ORIGINS = True` in local development.
3. **Verify API Gateway Forwarding**: Ensure `api-gateway/index.js` transparently forwards both `/api/v1/users/me` and `/api/v1/users/me/` without stripping path trailing slashes.

---

## 5. Verification Method

1. **Test Trailing Slash Behavior**:
   ```bash
   # Test request without trailing slash with Authorization header
   curl -i -H "Authorization: Bearer <valid_token>" http://localhost:8000/api/v1/users/me
   
   # Test request with trailing slash
   curl -i -H "Authorization: Bearer <valid_token>" http://localhost:8000/api/v1/users/me/
   ```
2. **Verify CORS Preflight**:
   ```bash
   curl -i -X OPTIONS http://localhost:8000/api/v1/users/me/ \
     -H "Access-Control-Request-Method: GET" \
     -H "Access-Control-Request-Headers: authorization" \
     -H "Origin: http://localhost:3000"
   ```
   Check that `Access-Control-Allow-Origin` and `Access-Control-Allow-Headers` respond with `200 OK` / `204 No Content`.
