# Pulse Medicare Render Deployment

## What is ready

- Render web service config is in `render.yaml`.
- The app starts with `gunicorn "app:app" --workers 1 --bind 0.0.0.0:$PORT`.
- `/healthz` is available for Render health checks.
- MySQL is read from environment variables. Secrets are not committed.

## MySQL options

Use one of these:

- A MySQL private service on Render, using Render's MySQL Docker template and a persistent disk.
- An external MySQL provider such as Aiven, Railway, AWS RDS, Clever Cloud, or your hosting provider.

The app supports either separate variables:

```env
MYSQL_HOST=
MYSQL_PORT=3306
MYSQL_USER=
MYSQL_PASSWORD=
MYSQL_DATABASE=pulse_medicare
MYSQL_SSL_MODE=REQUIRED
```

Or a single URL:

```env
MYSQL_URL=mysql://user:password@host:3306/pulse_medicare?ssl-mode=REQUIRED
```

If your MySQL provider requires a CA file, add it to Render as a secret file and set:

```env
MYSQL_SSL_CA=/etc/secrets/ca.pem
```

## Render steps

1. Push this repo to GitHub.
2. In Render, create a new Blueprint from this repo, or create a Python Web Service manually.
3. Use these commands if creating the service manually:

```bash
pip install -r requirements.txt
gunicorn "app:app" --workers 1 --bind 0.0.0.0:$PORT
```

4. Add these Render environment variables:

```env
MYSQL_REQUIRED=true
MYSQL_HOST=...
MYSQL_PORT=3306
MYSQL_USER=...
MYSQL_PASSWORD=...
MYSQL_DATABASE=pulse_medicare
```

5. Deploy. If MySQL cannot connect, the app will fail startup instead of silently running with temporary demo data.

## First login

On an empty connected MySQL database, the app seeds:

```text
username: admin
password: admin123
```

Change this password immediately after the first successful login.
