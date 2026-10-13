# AGENTS.md

This workspace contains two linked applications:

- [apex_frontend](apex_frontend): React + Vite frontend for the Apex platform.
- [apex_backend](apex_backend): Django + DRF + Channels backend with app-based modularization.

## Project structure

- Backend entry points: [apex_backend/manage.py](apex_backend/manage.py), [apex_backend/apex_backend/settings/base.py](apex_backend/apex_backend/settings/base.py), [apex_backend/apex_backend/urls.py](apex_backend/apex_backend/urls.py)
- Frontend entry points: [apex_frontend/src/main.jsx](apex_frontend/src/main.jsx), [apex_frontend/src/App.jsx](apex_frontend/src/App.jsx), [apex_frontend/src/api/axiosInstance.js](apex_frontend/src/api/axiosInstance.js)
- Backend app modules: [apex_backend/apps](apex_backend/apps) including accounts, profiles, cohorts, rankings, vendor, router, escrow, notifications, analytics, fraud, social, and trust_engine.

## Working conventions

- Keep changes local to the owning feature or app; avoid broad refactors or unrelated cleanup.
- When a behavior changes, verify both the backend contract and the frontend consumer before concluding the fix.
- Preserve auth, permissions, payment, escrow, anti-cheat, ranking, and notification safeguards; these are high-risk areas.
- If the model or API contract changes, update serializers, views, URLs, and tests together.
- Prefer schema-safe changes; if a database model changes, add or update the migration rather than editing generated files by hand.
- Do not weaken validation, security, or payment flow logic to satisfy a single test.

## Build and validation commands

### Frontend

```bash
cd apex_frontend
npm install
npm run dev
npm run build
npm run lint
```

### Backend

```bash
cd apex_backend
python manage.py check
python manage.py test
```

If a project-specific virtual environment is configured, use it instead of the system Python. By default the backend uses SQLite unless `DB_NAME` is set in the environment; production settings are configured in [apex_backend/apex_backend/settings](apex_backend/apex_backend/settings).

## Architecture notes

- Django REST Framework is configured with JWT auth in [apex_backend/apex_backend/settings/base.py](apex_backend/apex_backend/settings/base.py).
- The frontend uses a shared Axios instance that adds bearer tokens and refreshes expired JWTs in [apex_frontend/src/api/axiosInstance.js](apex_frontend/src/api/axiosInstance.js).
- The app is split by domain, and cross-app coordination is common for authentication, rankings, mentorship, escrow flows, cohort allocation, and notifications.
- Channels/Redis and Celery are part of the platform, so task and websocket-related changes may have backend side effects beyond the immediate feature area.

## Recommended workflow for agents

1. Identify the exact backend or frontend layer that owns the behavior.
2. Read only enough context to confirm the edit site and expected contract.
3. Make the smallest reversible fix.
4. Run the narrowest relevant validation command.
5. Review the final diff for contract mismatches or accidental scope expansion.

## Helpful starting points

- API and auth behavior: [apex_frontend/src/api](apex_frontend/src/api), [apex_backend/apps/accounts](apex_backend/apps/accounts)
- Cohort and mentorship flows: [apex_backend/apps/cohorts](apex_backend/apps/cohorts)
- Payments and escrow: [apex_backend/apps/escrow](apex_backend/apps/escrow)
- Rankings and trust scoring: [apex_backend/apps/rankings](apex_backend/apps/rankings), [apex_backend/apps/trust_engine](apex_backend/apps/trust_engine)
- Notifications and real-time events: [apex_backend/apps/notifications](apex_backend/apps/notifications)
- Frontend routes and pages: [apex_frontend/src/routes](apex_frontend/src/routes), [apex_frontend/src/pages](apex_frontend/src/pages)

When working in this repo, favor correctness, contract alignment, and minimal scope over broad cleanup.
