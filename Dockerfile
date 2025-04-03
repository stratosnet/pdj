FROM python:3.11-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.6.4 /uv /uvx /bin/

RUN mkdir -p /app
WORKDIR /app

ARG BUILD_LOCAL=false

ENV UV_COMPILE_BYTECODE=1
ENV UV_PROJECT_ENVIRONMENT=$HOME/".virtualenvs/app"
ENV PATH="$UV_PROJECT_ENVIRONMENT/bin:$PATH"

COPY pyproject.toml uv.lock /app/

# Installing dev tools
RUN if [ "$BUILD_LOCAL" = "true" ]; \
  then uv sync --frozen; \
  else uv sync --no-dev; \
  fi

COPY app/ /app/

EXPOSE 8000

CMD ["python", "manage.py", "0.0.0.0:8000"]
