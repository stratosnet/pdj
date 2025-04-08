from typing import Any

from ninja import Schema


class PayPalWebhookSchema(Schema):
    id: str
    create_time: str
    resource_type: str
    event_version: str
    event_type: str
    summary: str
    resource_version: str
    resource: dict[str, Any]
    links: list[dict[str, Any]]


class ErrorSchema(Schema):
    message: str
