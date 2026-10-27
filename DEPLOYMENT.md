# ApexStratos Deployment

## Current Architecture

- Frontend: React 18 and Vite 5; install with npm and build with `npm run build` from `apex_frontend`.
- Backend: Django 5.2, Django REST Framework, Channels and Daphne; dependencies are listed in `apex_backend/requirements.txt`.
- Database: PostgreSQL is selected with `DATABASE_URL` and is required in production. Development may use the existing SQLite database; legacy MySQL settings remain available for development only. PostgreSQL uses Django `JSONField` as native `jsonb`, and imported content packs are stored in the existing assessment, tutorial, and question models.
- Migrations: Django migrations, applied with `python manage.py migrate` only after a production backup and migration review.
- Existing process declaration: `apex_backend/Procfile` defines Daphne and a Celery worker. It does not establish that Pinnacle/cPanel supports Procfiles, Daphne, Redis or persistent workers.
- Frontend API: `/api/v1` by default. WebSockets use same-origin `ws:`/`wss:` unless `VITE_WS_BASE_URL` is set.
- Local Vite proxy: copy `apex_frontend/.env.example` to `.env`; set `VITE_DEV_API_TARGET` and `VITE_DEV_WS_TARGET` to the local backend. These proxy values are used only by the Vite development server. Set `VITE_API_BASE_URL` and, if needed, `VITE_WS_BASE_URL` to the production API origins in the production build environment; do not ship local `.env` files.
- Recovery repository: `https://github.com/fiddle254/Apex-loading.git`. Confirm the hosting deployment integration before deploying.

## Local Validation

From the repository root, install frontend dependencies with `npm ci` in `apex_frontend`. Run `npm run lint` and `npm run build` there.

Create and activate a Python virtual environment for the backend, install `apex_backend/requirements.txt`, then from `apex_backend` run:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py check --settings=apex_backend.settings.development
python manage.py test apps.cohorts.tests.test_assessment_integrity --settings=apex_backend.settings.development
python manage.py test apps.cohorts.tests.test_allocation --settings=apex_backend.settings.development
python manage.py test apps.cohorts.tests.test_content_import --settings=apex_backend.settings.development
```

To use PostgreSQL locally, create a database and set `DATABASE_URL` in `apex_backend/.env` (for example, `postgresql://apex_user:your-password@127.0.0.1:5432/apex_db`). Then run `python manage.py migrate --settings=apex_backend.settings.development`. PostgreSQL takes precedence over the legacy MySQL `DB_NAME` setting; SQLite remains the fallback when neither is configured. Switching from SQLite does not copy existing rows: back up and migrate data separately if it must be retained.

Content-pack JSON files are imported through the existing validated management commands, not loaded automatically at startup. Run a dry-run/preflight first; only apply validated packs after review. Existing model `JSONField` values, including learning objectives, options, and related IDs, use PostgreSQL `jsonb`.

Authorized administrators can inspect imported lesson text, question options, answer keys, and validation results from the frontend's **Admin tools → Assessment review** page. The page uses admin-only `/api/v1/cohorts/admin/content/` endpoints and enforces the draft → in-review → approved → published workflow for tutorials and Main Contest assessments; Sponsored View assessments must pass publication validation. Medical and Health and Law and Society still require qualified expert review before approval/publication. Invalid content packs must be corrected and revalidated before import; the review page does not bypass pack validation.

Admin accounts are provisioned only from **Admin tools → Users** or through the existing Django admin/management command. Public registration does not offer or accept the Admin account type. Existing users can be promoted or demoted by an administrator; account creation and role changes are recorded in the audit log.

## Vendor and Sponsorship Management

Apply the vendor migrations as part of a reviewed deployment with a database backup:

```powershell
python manage.py migrate --settings=apex_backend.settings.development
```

The module exposes authenticated onboarding and dashboard endpoints under `/api/v1/vendors/`, campaign CRUD, approval submission, asset, analytics and CSV-report endpoints under `/api/v1/campaigns/`, and administrator vendor/verification/campaign review endpoints under `/api/v1/admin/vendors/`. The React workspace is `/vendor`, the disclosed public campaign catalogue is `/campaigns`, and administrator review is **Admin tools → Vendors & campaigns**. Approved contest sponsorships are labelled in the contest interface without changing assessment content, scores, or awards. Vendor and campaign decisions use the existing in-app notification system and audit log. Verification files are stored separately from public media under `PRIVATE_UPLOAD_ROOT` (defaults to `apex_backend/private_uploads`); configure a persistent, access-restricted filesystem location in production, keep it outside all web-served roots, and back it up under the platform's sensitive-document retention policy. Do not replace this storage with public Cloudinary media storage.

Campaign budgets are proposed/approved amounts only. Billing, payment processing, invoices, spending ledgers and financial callbacks are not enabled; do not treat approved budget figures as payments or campaign spend. Campaign analytics count deduplicated, authenticated platform events and suppress aggregate reports below five unique authenticated viewers. The PostgreSQL migration and production document-storage persistence must be verified in the target environment before rollout.

Do not run seed, reset, flush or deletion commands against production.

## Assessment Content Import Status

The verified local SQLite import contains 1,504 complete assessment records and 15,040 questions across the three libraries. Nine source packs containing 656 assessments remain excluded because strict validation finds repeated prompts; those packs require meaningful content correction and revalidation. Three existing starter assessments in occupied schedule slots are preserved by the partial importer.

The importer is validation-only by default. Review a local preflight report with:

```powershell
python manage.py bootstrap_apexstratos_libraries --allow-partial --preserve-existing-slots --report-json .\assessment-preflight.json --settings=apex_backend.settings.development
```

The `--apply` and `--publish` options must not be used against production without an approved deployment, a database backup, and a zero-failure content report. Never publish Medical and Health or Law and Society content before its required qualified review. Reconcile database and API inventories after any import; a successful command alone does not establish that the target library is complete or published.

## Production Configuration

Set these in the hosting platform's protected environment-variable UI, not in Git:

- `DJANGO_SECRET_KEY`: newly generated production-only secret.
- `RENDER_EXTERNAL_HOSTNAME`: Render supplies the service hostname automatically and production settings add it to Django's allowed hosts.
- `ALLOWED_HOSTS`: optional comma-separated explicit hostnames, such as a custom backend domain; required when not running on Render. Wildcards are rejected.
- `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`: comma-separated HTTPS origins.
- `DATABASE_URL`: required PostgreSQL connection URL. Production startup rejects SQLite and MySQL; keep credentials in the protected environment configuration.
- `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`: required production SMTP configuration.
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`: legacy MySQL connection settings.
- `REDIS_URL`: production Redis URL if the deployed Channels/Celery features require Redis.
- `FRONTEND_URL`: production frontend base URL.
- `APEX_VERSION`, `GIT_COMMIT`: release label and exact deployed commit.
- Provider/storage/email values as required: `CLOUDINARY_*`, `STRIPE_*`, `MPESA_*`, `EMAIL_*`.

`apex_backend/.env.example` and `apex_frontend/.env.example` contain names only. Never upload local `.env` files or add secret values to GitHub. Rotate any credential that has ever been committed.

Production settings fail early unless PostgreSQL, secret, a Render-provided or explicitly configured host, HTTPS frontend/CSRF origins, SMTP, and HTTPS frontend URL are configured. `/health` returns `200` only when Django can connect to the configured database and otherwise returns `503`. `/version` returns only the configured release label and Git commit; it does not disclose secrets.

## Pinnacle/cPanel Setup To Confirm

No hosting control-panel access or provider configuration is available in this workspace. Before selecting an exact deployment procedure, confirm with Pinnacle/cPanel support:

1. Whether the account supports cPanel Git Version Control deployment from this GitHub repository, or requires SSH/manual upload.
2. Whether it supports a Python application with the required Python version, Django, ASGI/Daphne, Channels, WebSockets, Redis and Celery worker processes.
3. The provider-assigned application root, startup command, environment-variable interface, static-file mapping and SPA history fallback configuration.
4. The production database engine/version, backup procedure, migrations policy, outbound network and persistent-media policy.
5. TLS termination/proxy headers and the exact public API/WebSocket origin and callback URLs.

Do not assume Node/Python Application Manager, Procfile support, SSH access, Redis, or deployment hooks until the account confirms them. If the account only supports static frontend hosting and PHP, the current Django/Channels backend needs a separate compatible host; it cannot be deployed as a static cPanel site.

## Release, Verification and Rollback

1. Choose a release label and record the exact commit with `git rev-parse HEAD` after committing the tested source.
2. Build the frontend from that commit. Configure the hosting deployment to build or upload that exact commit, not a working directory snapshot.
3. Back up the production database using the host's supported backup tool. Review pending migrations and compatibility before applying them.
4. Deploy application code and required static assets; restart only using the provider-documented mechanism.
5. Set `APEX_VERSION` and `GIT_COMMIT` from that release. Confirm `/health`, `/version`, the homepage, authentication, API and WebSocket behavior on the public domain.
6. Keep the previous release commit/build available. If application verification fails, restore the prior code/build and configuration. Do not roll back or replace production data; use a forward fix for schema changes unless the database owner approves a tested recovery plan.

Live deployment and `https://Apexstratos.co.ke` verification require authorized hosting access and are not performed by local builds.