# BRIEFING — 2026-08-11T16:50:40Z

## Mission
Investigate routing, navigation, protected route guards, and duplicate/conflicting login flows across the codebase at /Users/apple/Desktop/ubuntunow-platform.

## 🔒 My Identity
- Archetype: explorer
- Roles: Teamwork preview explorer instance 2
- Working directory: /Users/apple/Desktop/ubuntunow-platform/.agents/explorer_m0_2
- Original parent: 079cd788-75fb-4316-a91b-100e4e486ae9
- Milestone: M0 (Survey & Architecture Mapping)

## 🔒 Key Constraints
- Read-only investigation — do NOT implement or modify source code
- Produce detailed handoff.md in working directory
- Communicate via send_message to parent (079cd788-75fb-4316-a91b-100e4e486ae9)

## Current Parent
- Conversation ID: 079cd788-75fb-4316-a91b-100e4e486ae9
- Updated: 2026-08-11T16:50:40Z

## Investigation State
- **Explored paths**: `api-gateway/index.js`, `auth-service/apps/users/urls.py`, `auth-service/apps/users/views.py`, `auth-service/config/urls.py`, `auth-service/config/settings/base.py`, `store-service/apps/users/urls.py`, `store-service/apps/users/views.py`, `store-service/config/urls.py`, `docker-compose.yml`, `test_api.py`, `test_local.py`
- **Key findings**:
  1. The repository at `/Users/apple/Desktop/ubuntunow-platform` is exclusively a Django/Node backend microservices repository containing 6 Django services + Node API Gateway (`api-gateway`). There is NO frontend UI code (React, Vue, HTML/JS SPA) in this repo.
  2. In `api-gateway/index.js`:
     - Line 38: `app.use(proxy('/api/v1/users', services.auth));` -> Routes `/api/v1/users/*` to auth-service (`:8001`).
     - Line 36: `app.use(proxy('/api/v1/users/store', services.store));` -> Routes `/api/v1/users/store/*` to store-service (`:8002`).
  3. In `auth-service/config/urls.py`:
     - Line 20: `path("api/v1/users/", include("apps.users.urls"))` -> maps `/api/v1/users/me/` to `CurrentUserView` (`IsAuthenticated`), `/api/v1/users/login` to `CustomTokenObtainPairView`, `/api/v1/users/token/refresh` to `TokenRefreshView`.
  4. Root cause analysis for frontend profile issue:
     - The profile API endpoint is `/api/v1/users/me/` (`auth-service/apps/users/urls.py:16`).
     - `CurrentUserView` requires JWT authentication via `Authorization: Bearer <access_token>` (`auth-service/config/settings/base.py:155`).
     - If the frontend app (hosted externally, e.g. `ubuntu-nexus-front.vercel.app` as per CORS settings in `base.py:213`) fails to attach `Authorization: Bearer <access_token>` or if the access token has expired (default lifetime 60m, `base.py:171`), backend returns HTTP 401 Unauthorized.
     - Upon HTTP 401 Unauthorized from `/api/v1/users/me/`, frontend router guard triggers redirection to login screen, causing secondary login prompt.
     - Additionally, API Gateway routing overlay: `/api/v1/users/store` routes to `store-service` while `/api/v1/users` routes to `auth-service`.
- **Unexplored areas**: None (all routes and Gateway rules inspected).

## Key Decisions Made
- Completed full analysis of backend routing, gateway routing, auth guard logic (`IsAuthenticated`), endpoint paths, and auth state persistence requirements.

## Artifact Index
- DISPATCH.md — User request dispatch
- BRIEFING.md — Working memory index
- progress.md — Progress log
- handoff.md — Comprehensive survey & analysis handoff report
