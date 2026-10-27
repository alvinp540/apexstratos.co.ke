# ApexStratos Codebase Audit

## Scope and evidence

This is an initial audit of the workspace at the start of the revision. It is based on the Django settings, account and cohort models/views, authentication client/context, content importer and its tests, escrow implementation, deployment notes, and local build/test commands. It is not a line-by-line security certification or a claim that every endpoint was tested.

The project directory was untracked in Git when inspected. No branch or commit checkpoint was created because doing so would require taking ownership of the existing untracked files, including the database and local dependencies.

## Current architecture

- **Frontend:** React 18, Vite 5, React Router 6, JavaScript/JSX and a shared Axios client. There is no TypeScript or Tailwind dependency in the current package manifest.
- **Backend:** Django 5.2, Django REST Framework, SimpleJWT, Channels, Celery and modular Django apps. The API is mounted under `/api/v1/`.
- **Persistence:** Django ORM with versioned migrations. The current settings require PostgreSQL via `DATABASE_URL`.
- **Authentication:** Custom UUID user model using email as the login identifier; JWT access and refresh tokens are stored by the browser in `localStorage`.
- **Domains present:** accounts/profiles, cohorts/tutorials/assessments, rankings/trust, vendor, escrow, notifications, analytics, fraud and social. Opportunity/support-programme code is partly in the cohorts domain rather than a standalone opportunities app.
- **Deployment:** Existing deployment notes describe a cPanel target but explicitly state that Python application management, PostgreSQL, Redis, WebSockets, workers and static routing need provider confirmation.

## Existing functionality observed

- Tutorial content has draft/review/publication states, schedule constraints, publication validation and user-owned progress/attempt records.
- The content-pack importer validates provenance, scheduling and question structure, creates draft content, and has tests for dry-run behavior, idempotent append-only imports, and ten-question records.
- Assessment scoring is performed in backend code. Existing tests confirm score calculation from server-held answers and disregard client-claimed video-watching time.
- Vendor, campaign, escrow, profile, notification, analytics and authentication API modules are present. Their presence alone does not establish complete or secure end-to-end workflows.
- A free subscription is created in the registration serializer. Public registration rejects the `admin` role, but other authorization and lifecycle concerns remain listed below.
- The existing local SQLite database and tutorial library are substantial user data and must not be reset or replaced as part of a database migration.

## Incomplete or defective areas

1. **Production configuration — addressed in this revision:** previously, production imported settings that could fall back to SQLite and a development secret. Production now requires a PostgreSQL URL, non-empty secret, explicit hostnames, HTTPS CORS/CSRF origins, HTTPS frontend URL and SMTP credentials. The production deployment notes and environment example were aligned.
2. **Authentication lifecycle:** registration marks accounts verified when `EMAIL_HOST_USER` is absent, including production before the settings hardening; verification/reset task dispatch exceptions are swallowed. A production deployment now requires SMTP configuration, but registration delivery/error handling and verification-token lifecycle still need focused correction and tests.
3. **Browser credential exposure:** both JWTs are stored in `localStorage`; a script injection could read the refresh credential. Move to an appropriately protected refresh-cookie design with CSRF handling, or document a deliberate alternative with a threat model.
4. **Account identity:** email uniqueness is a database unique constraint but case-insensitive normalization is not established. `role` includes `admin`, so privileged account creation and role-change pathways need review across all serializers/admin operations.
5. **Payments and escrow:** the inspected M-Pesa callback trusts callback fields and catches processing errors without surfacing them; amount/currency verification, authenticated provider proof, idempotent event storage and transaction locking need a dedicated payment-integrity pass. Do not enable live payment claims until that work and provider testing are complete.
6. **Product architecture mismatch:** the brief requests TypeScript, Tailwind and dedicated feature domains, while current frontend is JavaScript/JSX and the backend centralizes some learning/opportunity behavior in cohorts. This needs gradual migration rather than a scaffold replacement.
7. **API contract/testing:** frontend and backend use many operational endpoints, but no OpenAPI package is listed. The automated suite currently reports 24 tests, concentrated in cohorts; there are no observed account-specific tests or frontend test script.
8. **Data migration:** PostgreSQL is supported by dependency and settings, but no verified SQLite-to-PostgreSQL data migration procedure or production PostgreSQL connectivity is available. Migration history starts with the custom user model, making any identity-schema redesign a high-risk data migration.
9. **Hosting:** the workspace cannot establish the cPanel account's enabled Python/Passenger, PostgreSQL, persistent storage, Redis, worker, TLS proxy or SPA fallback capabilities. Deployment success cannot be asserted without provider access.

## Database and migration concerns

- Preserve `apex_backend/db.sqlite3`; do not run reset/flush/seed or destructive migrations against it.
- `makemigrations --check --dry-run` reported no model changes pending migration at audit time.
- Production is now configured to refuse SQLite/MySQL rather than silently start on a different empty database.
- Before any production schema change, take a provider-supported backup, review generated migration operations, test against a copy, and separately plan data transfer and reconciliation.
- Existing model choices include JSON fields, UUID keys, decimal payment values and several uniqueness constraints; PostgreSQL compatibility is plausible but still requires running migrations and tests against an actual PostgreSQL instance.

## Frontend/backend integration

- The frontend uses a centralized Axios client with bearer-token attachment and one refresh retry path.
- Routes include public landing/login/register/campaign catalogue and authenticated dashboard, learning, contests, merit, opportunities, profile, notifications, admin and vendor pages.
- `VITE_API_BASE_URL` is supported; Vite development proxies `/api` and `/ws`.
- No frontend component/integration test runner is configured in `package.json`. Operational routes should be audited feature-by-feature against real API contracts before claiming complete journeys.

## Verification baseline

Executed in this workspace:

- `python manage.py check` using the project virtual environment: passed.
- `python manage.py test`: 24 tests passed.
- `python manage.py makemigrations --check --dry-run`: no changes detected.
- `npm.cmd run lint`: passed.
- `npm.cmd run build`: passed.

The backend test run emitted a warning that `staticfiles/` did not exist. PostgreSQL, production SMTP, cPanel deployment, full authentication journeys and external provider callbacks were not tested.

## Recommended revision sequence

See [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md). Prioritize production safety and credential handling, then identity and content/assessment workflows, followed by payment integrity, organization/opportunity workflows, API contracts and cPanel verification. Keep every change incremental and backed by a migration and focused tests where required.
