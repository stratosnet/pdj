# Production Deployment Guide for Payment Service

## Overview

This guide provides instructions for deploying the payment service using Docker Compose in a production environment.

## Docker Compose Setup

The quickstart Docker image is an all-in-one container launching the PDJ server, the PDJ worker for background jobs and a Redis server to schedule those jobs. While suitable for local development and testing, it's usually better in production to have dedicated containers for each purpose.

Docker Compose greatly simplifies the configuration of multiple containers. This is probably the easiest way if you already know Docker and want to deploy on your own server. You'll find typical [docker-compose.yml](https://github.com/stratosnet/pdj/docker-compose.yml) configuration for PDJ.

## Post-deployment Setup

After launching the containers, some initialization steps are required to prepare the database and static files:

```
docker compose exec pdj_server ./manage.py migrate
docker compose exec pdj_server ./manage.py init_data
docker compose exec pdj_server ./manage.py collectstatic --noinput
```

These commands will:

- Apply database migrations

- Initialize essential data for the application

- Collect static files into the designated volume for serving through Nginx

Make sure the containers are running before executing these commands.

## PDJ containers

We have 3 PDJ containers: one for the admin and api server (pdj_server), second for the celery worker to proceed background tasks (pd_worker) and last one for periodic celery task scheduler (pdj_beat). All are required to make PDJ working correctly.

## Database and Redis containers

We also defined a dedicated database container, PostgreSQL, and a broker for passing job messages, Redis. Note how we defined and linked a volume for both of them. By doing this, we make sure we persist our data in a dedicated Docker volume that will persist even if we delete the containers.

## Nginx reverse proxy (through certbot)

A reverse proxy is a specialized software able to accept incoming HTTP requests and route them to the underlying applications. It acts as the unique HTTP entrypoint to our system. Here, it'll simply route requests with the domain pdj.mydomain.com to the pdj_server container.

It's also in charge for managing SSL certificates. In this configuration, nginx-certbot container will automatically issue a free Let's Encrypt certificate for the domain pdj.mydomain.com, using the TLS challenge. nginx-certbot supports other types of challenge that may be more suitable for your use-case. The volume nginx_secrets is here to store the generated certificates.

We strongly suggest you to read more about how to configure nginx-certbot with Docker Compose: https://github.com/JonasAlfredsson/docker-nginx-certbot/blob/master/examples
