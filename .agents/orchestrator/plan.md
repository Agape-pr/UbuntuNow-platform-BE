# Plan: Fix Auth Persistence & Eliminate Conflicting Login Flows

## Architecture & Problem Overview
The project at `/Users/apple/Desktop/ubuntunow-platform` is a microservices platform (Node.js API Gateway + Django microservices).
Step 0 Survey revealed the dual root causes of the auth persistence failure and secondary login prompt:
1. **Trailing Slash Mismatch**: `auth-service/apps/users/urls.py` enforces `path('me/', ...)`. Requests to `/api/v1/users/me` trigger a HTTP 301 redirect to `/api/v1/users/me/`, which causes standard HTTP fetch clients to drop the `Authorization: Bearer <token>` header, returning HTTP 401 Unauthorized and redirecting the user to a secondary login prompt.
2. **Hardcoded CORS Origins**: `auth-service/config/settings/base.py` and `product-service/config/settings/base.py` hardcode `CORS_ALLOWED_ORIGINS` at the bottom of `base.py`, overriding env vars and blocking CORS preflight (`OPTIONS`) requests from frontend dev servers (e.g. `localhost:3000`, `5173`, `8000`).

## Feature Inventory
| # | Feature / Issue | Description | Milestone | Source |
|---|-----------------|-------------|-----------|--------|
| 1 | Auth Codebase Mapping | Discover microservices, gateway routing, Django auth views, token validation | M0 (Survey) | ORIGINAL_REQUEST |
| 2 | Trailing Slash & Auth Persistence | Support both `/api/v1/users/me` and `/api/v1/users/me/` without 301 header stripping; ensure JWT tokens persist on protected requests | M1 | R1 |
| 3 | CORS & Unified Auth Flow | Make CORS configurable via env vars, eliminate 401 unauthorized triggers caused by preflight failures / 301 redirects | M2 | R2 |
| 4 | Verification & Hardening | Run Django / API Gateway servers, verify token persistence & `/profile` / `/api/v1/users/me` response via test scripts, run challenger & auditor | M3 | Acceptance Criteria |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M0 | Survey & Architecture Mapping | Map codebase, identify trailing slash redirect bug & hardcoded CORS origins | None | DONE |
| M1 | Resolve Auth State Persistence | Update `auth-service/apps/users/urls.py` to support `me` and `me/` without 301 redirects; ensure JWT stateless auth validates headers | M0 | DONE |
| M2 | Eliminate Conflicting Login Flows | Consolidate CORS settings across microservices (`base.py`), ensure API gateway forwards headers/paths transparently | M0, M1 | DONE |
| M3 | End-to-End Verification & Gate | Run test scripts (`test_api.py`, `test_local.py`, etc.), execute challenger & auditor validation, ensure zero regression | M1, M2 | DONE |


## Interface Contracts & Layout
- `GET /api/v1/users/me` & `GET /api/v1/users/me/`: Returns HTTP 200 with user detail JSON when `Authorization: Bearer <access_token>` is present. Must NOT return HTTP 301 or HTTP 401.
- `POST /api/v1/users/login`: Accepts credentials, returns `{ access, refresh, user }`.
- Code Layout:
  - `auth-service/apps/users/urls.py`: URL patterns for login, token refresh, and user profile (`me`/`me/`).
  - `auth-service/config/settings/base.py`: CORS and DRF configuration.
  - `product-service/config/settings/base.py`: CORS configuration.
  - `api-gateway/index.js`: Express proxy routes.

