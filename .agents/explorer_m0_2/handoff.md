# Handoff Report: Routing, Navigation & Auth Guard Analysis (M0 Survey)

## 1. Observation

### Codebase Architecture & File Locations
1. **Repository Scope**:
   - Location: `/Users/apple/Desktop/ubuntunow-platform`
   - Structure: Polyglot microservices workspace containing Node.js API Gateway and 6 Django Python microservices (`auth-service`, `store-service`, `product-service`, `order-service`, `payment-service`, `notification-service`).
   - Frontend presence: **No frontend UI source code (React, Vue, HTML)** exists inside this repository. The frontend application is hosted externally (referenced in CORS configuration as `https://ubuntu-nexus-front.vercel.app` and `http://localhost:8080`).

2. **API Gateway Route Definitions**:
   - File: `/Users/apple/Desktop/ubuntunow-platform/api-gateway/index.js`
   - Line 15-22: Service URLs defined (`auth-service` at port 8001, `store-service` at port 8002).
   - Line 35: `app.use(proxy('/api/v1/auth', services.auth));`
   - Line 36: `app.use(proxy('/api/v1/users/store', services.store));`
   - Line 38: `app.use(proxy('/api/v1/users', services.auth));`

3. **Backend Profile & Auth Endpoints (`auth-service`)**:
   - URL Configuration: `/Users/apple/Desktop/ubuntunow-platform/auth-service/config/urls.py`
     - Line 19: `path("api/v1/auth/", include("apps.authentication.urls"))`
     - Line 20: `path("api/v1/users/", include("apps.users.urls"))`
   - Users App Routes: `/Users/apple/Desktop/ubuntunow-platform/auth-service/apps/users/urls.py`
     - Line 13: `path('register', RegisterView.as_view(), name='register')` -> `/api/v1/users/register`
     - Line 14: `path('login', CustomTokenObtainPairView.as_view(), name='token_obtain_pair')` -> `/api/v1/users/login`
     - Line 15: `path('token/refresh', TokenRefreshView.as_view(), name='token_refresh')` -> `/api/v1/users/token/refresh`
     - Line 16: `path('me/', CurrentUserView.as_view(), name='user-me')` -> `/api/v1/users/me/` (Profile endpoint)

4. **Auth Guard & Authentication Class Settings**:
   - Backend Auth Settings: `/Users/apple/Desktop/ubuntunow-platform/auth-service/config/settings/base.py`
     - Lines 154-158:
       ```python
       REST_FRAMEWORK = {
           'DEFAULT_AUTHENTICATION_CLASSES': (
               'rest_framework_simplejwt.authentication.JWTAuthentication',
           ),
           ...
       }
       ```
     - Lines 170-173:
       ```python
       SIMPLE_JWT = {
           'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
           'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
       }
       ```
   - Profile View Auth Guard: `/Users/apple/Desktop/ubuntunow-platform/auth-service/apps/users/views.py`
     - Lines 41-46:
       ```python
       class CurrentUserView(generics.RetrieveUpdateAPIView):
           serializer_class = UserDetailSerializer
           permission_classes = [IsAuthenticated]

           def get_object(self):
               return self.request.user
       ```

5. **Existing API Integration Scripts**:
   - File: `/Users/apple/Desktop/ubuntunow-platform/test_api.py`
     - Line 3: `BASE_URL = "https://api-gatewayubuntunow-platform-be-production.up.railway.app/api/v1"`
     - Lines 17-22: Obtains JWT access token via `POST /users/login` with payload `{"username": email, "password": password}`.
     - Lines 26-37: Accesses profile endpoint `/users/me/` attaching header `Authorization: Bearer <token>`.

---

## 2. Logic Chain

1. **Observation 1 & 3**: Navigating to `/profile` on the frontend client triggers an API fetch call to the user profile endpoint `/api/v1/users/me/` on `auth-service` via `api-gateway`.
2. **Observation 4**: The `CurrentUserView` endpoint at `/api/v1/users/me/` strictly enforces `permission_classes = [IsAuthenticated]` using SimpleJWT authentication (`rest_framework_simplejwt.authentication.JWTAuthentication`).
3. **Observation 4 & 5**: `JWTAuthentication` inspects incoming HTTP requests for an `Authorization: Bearer <access_token>` header.
   - If the client request lacks the `Authorization` header, or passes an invalid/expired token: Django REST Framework returns HTTP `401 Unauthorized` (`{"detail": "Authentication credentials were not provided."}` or `{"detail": "Given token not valid for any token type"}`).
4. **Root Cause Analysis (Secondary Login Prompt Trigger)**:
   - When a user logs in, `POST /api/v1/users/login` returns an `access` JWT token (and `refresh` token).
   - If the client application fails to store the token (e.g. in `localStorage` or memory) or fails to attach `Authorization: Bearer <access_token>` when navigating to `/profile`, the backend returns HTTP 401 Unauthorized.
   - In standard SPA/client router guard logic (axios interceptors or React Router / Vue Router guards), receiving HTTP 401 Unauthorized from a protected resource (like `/profile` calling `/api/v1/users/me/`) automatically redirects the user to `/login` or opens a secondary login modal prompt.
5. **Gateway Routing Overlay**:
   - `api-gateway/index.js` routes `/api/v1/users/store` to `store-service` (port 8002) and `/api/v1/users` to `auth-service` (port 8001).
   - Order matching in Express `api-gateway/index.js` puts `/api/v1/users/store` (line 36) before `/api/v1/users` (line 38), which is correctly ordered. However, if a request to `/api/v1/users/me/` is sent without token headers, `auth-service` rejects it with 401, causing the frontend auth guard to trigger re-authentication.

---

## 3. Caveats

- **External Frontend Client**: The client application (React/NextJS/Vue) consuming this API is not located in this repository. All observations about frontend navigation, router guards, and UI modals are deduced from API endpoints, HTTP status behaviors, CORS configuration (`https://ubuntu-nexus-front.vercel.app`), and test scripts (`test_api.py`).
- **Token Expiration**: Access token lifetime is set to 60 minutes (`base.py:171`). If refresh token flow is not automatically triggered upon 401, the user will be prompted to log in again.

---

## 4. Conclusion

- **Exact File Paths**:
  - API Gateway Routing: `/Users/apple/Desktop/ubuntunow-platform/api-gateway/index.js`
  - Auth URL Configuration: `/Users/apple/Desktop/ubuntunow-platform/auth-service/config/urls.py`
  - Users URL Definitions: `/Users/apple/Desktop/ubuntunow-platform/auth-service/apps/users/urls.py`
  - Profile View & Auth Guard: `/Users/apple/Desktop/ubuntunow-platform/auth-service/apps/users/views.py` (lines 41-46, `CurrentUserView` using `IsAuthenticated`)
  - Auth Settings & JWT Config: `/Users/apple/Desktop/ubuntunow-platform/auth-service/config/settings/base.py` (lines 154-174)
- **Primary Auth Finding**:
  - The profile backend endpoint is `/api/v1/users/me/`.
  - The profile endpoint requires a valid JWT token sent in `Authorization: Bearer <token>`.
  - Secondary login prompts on profile navigation occur because requests to `/api/v1/users/me/` lack a valid authorization header, causing a 401 Unauthorized response from `auth-service`, which triggers client-side redirect guards to prompt for login again.

- **Recommended Fix Strategy**:
  1. Ensure auth state (JWT access token) is properly retained and attached in HTTP client headers for protected route requests such as `/api/v1/users/me/`.
  2. Ensure `/api/v1/users/token/refresh` is utilized seamlessly when access tokens expire.
  3. Verify that `api-gateway` routes `/api/v1/users/me/` cleanly to `auth-service` without stripping authorization headers.

---

## 5. Verification Method

1. **Direct Backend API Verification**:
   - Run `auth-service` locally or via test script.
   - Execute HTTP POST to `http://localhost:8000/api/v1/users/login` (or port 8001) with valid credentials to obtain `access` token.
   - Execute HTTP GET to `http://localhost:8000/api/v1/users/me/` without `Authorization` header -> verify it returns `HTTP 401 Unauthorized`.
   - Execute HTTP GET to `http://localhost:8000/api/v1/users/me/` with `Authorization: Bearer <token>` -> verify it returns `HTTP 200 OK` with user profile details.
2. **Automated Test Script**:
   - Run `python test_api.py` or equivalent integration test to verify token issuance and profile retrieval.
