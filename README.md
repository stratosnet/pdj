# Payment service

### Requirements

- [docker](https://docs.docker.com/engine/install/)

### How to get local setup?

1. **Create base `.env` file**

   ```
   cp .env.copy .env
   ```

2. **Run the project**

   ```
   docker compose -f docker-compose.local.yml up -d
   ```

3. **Initialize migrations**

   ```
   docker compose -f docker-compose.local.yml exec web ./manage.py migrate
   ```

4. **Create superuser (for admin panel at `/admin/`)**

   ```
   docker compose -f docker-compose.local.yml exec web ./manage.py createsuperuser
   ```

### Production NOTES (required)

For production (where Nginx is serving the static files), it is required to collect static files:

```
docker compose exec web ./manage.py collectstatic --noinput
```

To verify email Sentry (not yet implemented, but will be):

```
curl http://localhost:9070/sentry-debug/
```
