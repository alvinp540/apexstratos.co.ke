# ApexStratos Implementation Plan

This plan follows the existing modular project and preserves its local database and content. It is a staged plan, not a claim that all requested functionality is already implemented.

## Stage A — Audit and recovery

- [x] Inspect the repository structure, current Git status, settings, authentication, content import, key domain models and deployment notes.
- [x] Record verified architecture, risks, existing checks and constraints in [CODEBASE_AUDIT.md](./CODEBASE_AUDIT.md).
- [x] Preserve the untracked workspace as-is; do not stage, commit, reset or replace its database.

## Stage B — Foundation

- [x] Require production PostgreSQL, explicit allowed hosts, HTTPS frontend/CORS/CSRF origins, a configured secret and SMTP settings.
- [x] Align deployment documentation and `.env.example` with production requirements.
- [ ] Add automated production-settings validation tests.
- [ ] Verify migrations and database behavior against an actual PostgreSQL service.
- [ ] Align frontend API error handling and document/version the API contract.

## Stage C — Identity and profiles

- [ ] Replace browser-persisted refresh tokens with an HttpOnly refresh-cookie flow and CSRF protection, or document and test an accepted alternative.
- [ ] Ensure production registration never verifies an account without proof; make email task delivery failures observable and recoverable.
- [ ] Add tests for registration, verification, login/logout, password recovery, rate limiting, role assignment and account isolation.
- [ ] Normalize email identity consistently without losing existing users; first inventory collisions and prepare a reversible migration.
- [ ] Review editable profile fields and organization membership permissions.

## Stage D — Learning and content

- [ ] Preserve official capability-field definitions and current imported records.
- [ ] Review importer validation, content provenance and publication permissions against all content libraries.
- [ ] Add regression cases for malformed schedules, duplicate records, draft exclusion and authorized review transitions.
- [ ] Verify public lesson output never reveals correct answers outside an owned, submitted attempt.

## Stage E — Assessments and merit

- [ ] Add API tests for attempt ownership, versioning, server-side scores, retries, idempotency and answer disclosure.
- [ ] Trace existing ranking/trust/merit behavior and document current award rules before changing them.
- [ ] Add auditable, duplicate-safe merit events only after business rules are confirmed.

## Stage F — Vendors and sponsorships

- [ ] Review all campaign transitions, verification ownership, private file access and audit records.
- [ ] Distinguish approved budgets from actual processed payments and verified outcomes.
- [ ] Add role/object-scope tests for vendor and reviewer workflows.

## Stage G — Organizations and opportunities

- [ ] Inventory existing support/opportunity endpoints and their current placement in the cohorts domain.
- [ ] Add organization membership scoping, eligibility explanations, deadline enforcement and application transition tests.
- [ ] Do not create a parallel opportunity model before confirming the existing model/API contract.

## Stage H — Payments and notifications

- [ ] Persist provider webhook events with unique provider IDs and process them transactionally/idempotently.
- [ ] Verify provider signatures, amount, currency, merchant reference and ownership before changing payment/entitlement state.
- [ ] Surface callback failures through logs/monitoring without exposing secrets or sensitive payloads.
- [ ] Add notification ownership and deduplication tests.

## Stage I — Frontend and release

- [ ] Add frontend test/type-checking only as part of a planned migration; first preserve the current React/Vite behavior and component design.
- [ ] Incrementally adopt TypeScript/Tailwind only after API and design contracts are established; do not rewrite the app as a disconnected scaffold.
- [ ] Confirm cPanel Python/Passenger, PostgreSQL, static routing, persistent uploads, TLS proxy and worker capabilities with the account provider.
- [ ] Run the full journey tests and release checklist against a non-production deployment before production migration.
- [ ] Maintain architecture, security, database and cPanel-specific deployment documents as each implementation stage is verified.

## Current checkpoint

The audit is complete and production settings now fail closed on missing core deployment configuration. After the change, all 24 backend tests passed, migration checks reported no pending changes, production settings rejected missing database configuration, and a placeholder PostgreSQL configuration passed Django checks with `DEBUG=False`. Frontend lint and build passed. No live database, SMTP provider, payment provider or cPanel configuration was accessed.
