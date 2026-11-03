# ApexStratos

ApexStratos is a learning and assessment platform with separate React and Django applications. The frontend provides the student, vendor, and administrator experiences; the backend serves the API and handles authentication, assessments, cohort and reward workflows, notifications, and related platform services.

## Project structure

| Path | Description |
| --- | --- |
| `apex_frontend/` | React 18, Vite, and Tailwind CSS web application |
| `apex_backend/` | Django REST Framework and Channels API |
| `apex_backend/apps/` | Domain apps, including accounts, cohorts, escrow, vendor, rankings, notifications, and analytics |
| `docs/` | Project audit and implementation notes |
| `DEPLOYMENT.md` | Deployment architecture, configuration, and operational guidance |

## Requirements

- Node.js and npm
- Python 3.11 or newer
- PostgreSQL
- Redis for production channel layers and background workers

## Local development

### 1. Configure the backend

In PowerShell, from the repository root:

```powershell
cd apex_backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `apex_backend/.env` and set at least `DATABASE_URL` to a PostgreSQL connection. Other integrations, such as Redis, email, Cloudinary, and payment providers, require their corresponding environment variables when those services are used. Do not commit `.env` files or credentials.

Apply migrations and start the API:

```powershell
python manage.py migrate --settings=apex_backend.settings.development
python manage.py runserver
```

### 2. Configure and run the frontend

Open a second PowerShell terminal from the repository root:

```powershell
cd apex_frontend
npm ci
Copy-Item .env.example .env
npm run dev
```

The Vite development server starts at `http://localhost:5173`. Its API and WebSocket proxy targets can be changed with `VITE_DEV_API_TARGET` and `VITE_DEV_WS_TARGET` in `apex_frontend/.env`. The backend defaults to `http://127.0.0.1:8000`.

## Validation

Run frontend checks from `apex_frontend/`:

```powershell
npm run lint
npm run build
```

Run backend checks from `apex_backend/` with the virtual environment activated:

```powershell
python manage.py check --settings=apex_backend.settings.development
python manage.py test --settings=apex_backend.settings.development
```

## Production and deployment

The production backend requires PostgreSQL and explicit production settings, including `DATABASE_URL`, `DJANGO_SECRET_KEY`, allowed hosts, HTTPS CORS/CSRF origins, and `FRONTEND_URL`. Configure any enabled integrations using the environment variables documented in `apex_backend/.env.example`. The frontend can use `VITE_API_BASE_URL` and `VITE_WS_BASE_URL` for the deployed API origins.

See [DEPLOYMENT.md](./DEPLOYMENT.md) for deployment requirements, migration precautions, API configuration, and operational guidance. Take and verify a database backup before applying production migrations.

## Security

- Never commit secrets, credentials, production data, or populated environment files.
- Use `apex_backend.settings.production` only with its required production configuration.
- Review payment, reward, and migration changes carefully before deploying.
