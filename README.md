# ConstructSaaS

One Django REST/Channels backend serves the React web application.

## Local setup

```powershell
$python312 = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
& $python312 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo_data

cd frontend
npm install
npm run build
cd ..

python -m daphne -b 127.0.0.1 -p 8000 construction_saas.asgi:application
```

Open `http://127.0.0.1:8000/`. Local development uses SQLite and the in-memory
channel layer. Set `DATABASE_URL`, `REDIS_URL`, `DJANGO_SECRET_KEY`,
`DJANGO_ALLOWED_HOSTS`, and `DJANGO_DEBUG=false` for deployment.

## Documentation

- [Complete website user and operations manual](docs/WEBSITE_USER_MANUAL.md)
- [Architecture guide](docs/ARCHITECTURE.md)
- [Release checklist](docs/RELEASE_CHECKLIST.md)
- [Finance API reference](docs/finance-api.md)

## Render deployment

This repository includes `render.yaml` for a Django web service, PostgreSQL
database, and Render Key Value channel layer. In Render, create a new Blueprint
from this GitHub repository and apply the blueprint. Set the SMTP variables and
any custom-domain values in the service environment before inviting users.
