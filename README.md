# PDJ [![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3110/)![t](https://img.shields.io/badge/status-maintained-yellow.svg)[![License: Elastic License 2.0](https://img.shields.io/badge/license-Elastic%202.0-blue.svg)](https://github.com/stratosnet/pdj/blob/master/LICENSE.md)

<p align="center">
  <img src="https://raw.githubusercontent.com/stratosnet/pdj/refs/heads/main/.github/logos/dj_logo.png" alt="PDJ" width="128">
</p>

<p align="center">
    <em>PDJ - Service to manage subscriptions for providers in one place</em>
</p>

## Motivation

The main motivation was to build a simple microservice to manage subscriptions, with the potential to extend it later to include feature planning — all in one place.
There are two API tags: one for the frontend (e.g., order checkout, subscriptions) and another for backend usage (e.g., polling user subscriptions for sync).
We aimed for a lightweight API — as an alternative to complex solutions like HypeSwitch or Kill Bill — while still providing admin capabilities by using Django as the core framework.

## Available payment providers

- PayPal
- Stripe (in TODO)

## Getting started

- Development (and for quick run): [dev](https://github.com/stratosnet/pdj#development)
- FAQ: [faq](https://github.com/stratosnet/pdj/blob/main/docs/faq.md)
- Environment configuration: [env](https://github.com/stratosnet/pdj/blob/main/docs/config.md)
- Production setup: [prod](https://github.com/stratosnet/pdj/blob/main/docs/production.md)

## Development

To get started quickly, we recommend you to use and launch project through docker compose. There is some short steps.

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
   docker compose -f docker-compose.local.yml exec pdj_server ./manage.py migrate
   ```

4. **Create init data**

   ```
   docker compose -f docker-compose.local.yml exec pdj_server ./manage.py init_data
   ```

## Contributing

All contributions to improve the project are welcome! In particular, new providers, bug and documentation fixes are really appreciated.

## License

PDJ is [fair-code](http://faircode.io) distributed under [**Elastic License 2.0 (ELv2)**](https://github.com/stratosnet/pdj/blob/main/LICENSE.md).
