# 📄 Environment Variables Reference

This document describes the environment variables used in the project, along with their default values.

---

## 🛠 General

| Variable                | Default | Description                                                                      |
| ----------------------- | ------- | -------------------------------------------------------------------------------- |
| `DEBUG`                 | `false` | Enables Django debug mode (should be `false` in production).                     |
| `SECRET_KEY`            | –       | Django's secret key for cryptographic signing. Keep it secure.                   |
| `ALLOWED_HOSTS`         | `[]`    | Comma-separated list of allowed hosts. Use `*` for all (not safe in production). |
| `DEBUG_TOOLBAR_ENABLED` | –       | Enables Django Debug Toolbar if `true`.                                          |
| `SENTRY_DSN`            | –       | DSN for Sentry error reporting. Leave empty to disable.                          |
| `DEFAULT_CURRENCY`      | `"USD"` | Default currency used for transactions.                                          |
| `PDJ_TITLE_NAME`        | `PDJ`   | The service title displayed in templates and admin panel.                        |

---

## 🗄 Database

| Variable       | Default | Description                                                                                |
| -------------- | ------- | ------------------------------------------------------------------------------------------ |
| `DATABASE_DSN` | –       | Connection string to PostgreSQL DB in the format: `psql://user:password@host:port/dbname`. |

---

## 🔐 SSO / OIDC

| Variable             | Default | Description                                               |
| -------------------- | ------- | --------------------------------------------------------- |
| `OIDC_ISSUER_URI`    | –       | URL of the OIDC identity provider (e.g., Keycloak, Fief). |
| `OIDC_CLIENT_ID`     | –       | OIDC client ID used for authentication.                   |
| `OIDC_CLIENT_SECRET` | –       | OIDC client secret used for authentication.               |

---

## 🌐 Application

| Variable                 | Default | Description                                         |
| ------------------------ | ------- | --------------------------------------------------- |
| `PDJ_DOMAIN`             | –       | Public domain or ngrok URL where the app is hosted. |
| `PDJ_MAIN_USER_EMAIL`    | –       | Email for the default admin user.                   |
| `PDJ_MAIN_USER_PASSWORD` | –       | Password for the default admin user.                |

---

## 💳 Payment (PayPal)

| Variable                     | Default | Description                                       |
| ---------------------------- | ------- | ------------------------------------------------- |
| `PDJ_PAYPAL_CLIENT_ID`       | –       | PayPal client ID for the application.             |
| `PDJ_PAYPAL_CLIENT_SECRET`   | –       | PayPal client secret for the application.         |
| `PDJ_PAYPAL_ENDPOINT_SECRET` | –       | PayPal webhook signature secret for verification. |
| `PDJ_PAYPAL_IS_SANDBOX`      | `true`  | If `true`, uses PayPal sandbox environment.       |

---

## 🔑 Internal Auth

| Variable            | Default | Description                                                |
| ------------------- | ------- | ---------------------------------------------------------- |
| `PDJ_CLIENT_ID`     | –       | Internal API client ID for server-to-server communication. |
| `PDJ_CLIENT_SECRET` | –       | Internal API client secret.                                |

---

## 📧 Email

| Variable              | Default                                          | Description                                                                                                                                                  |
| --------------------- | ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `DEFAULT_FROM_EMAIL`  | `webmaster@pdj.com`                              | Default email address for sending emails.                                                                                                                    |
| `EMAIL_BACKEND`       | `django.core.mail.backends.console.EmailBackend` | Django backend used for email. See [Django Docs](https://docs.djangoproject.com/en/5.1/topics/email/#obtaining-an-instance-of-an-email-backend) for details. |
| `EMAIL_HOST`          | `localhost`                                      | SMTP server host.                                                                                                                                            |
| `EMAIL_PORT`          | `25`                                             | SMTP server port.                                                                                                                                            |
| `EMAIL_HOST_USER`     | `""`                                             | SMTP login (can be empty).                                                                                                                                   |
| `EMAIL_HOST_PASSWORD` | `""`                                             | SMTP password or API key.                                                                                                                                    |
| `EMAIL_USE_TLS`       | `false`                                          | Use TLS encryption. Recommended: `true`.                                                                                                                     |

---

## 🧵 Celery

| Variable                | Default                | Description                                   |
| ----------------------- | ---------------------- | --------------------------------------------- |
| `CELERY_RESULT_BACKEND` | `redis://redis:6379/1` | URL for Redis backend to store task results.  |
| `CELERY_BROKER_URL`     | `redis://redis:6379/2` | Redis broker URL used for distributing tasks. |
