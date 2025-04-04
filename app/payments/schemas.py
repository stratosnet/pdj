from typing import Any
from ninja import Schema


class CheckoutSchema(Schema):
    plan_id: int
    payment_method_id: int


class UnsubscribeSchema(Schema):
    id: int
    reason: str


class SwsubscribeSchema(Schema):
    from_subscription_id: int
    to_subscription_id: str


class LinkSchema(Schema):
    url: str


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
