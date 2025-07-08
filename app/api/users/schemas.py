import uuid
import re
from ninja import Schema, ModelSchema, Field
from pydantic import ValidationInfo, field_validator
from django.http import HttpRequest
from django.conf import settings

from accounts.models import User, Client
from payments.models import Subscription


class SubscriptionSchema(ModelSchema):
    plan_id: uuid.UUID
    status: str = Field(..., alias="get_status_display")

    class Meta:
        model = Subscription
        fields = [
            "id",
            "start_at",
            "end_at",
            "suspended_at",
            "next_billing_at",
            "next_billing_plan",
            "created_at",
        ]


class MeSchema(ModelSchema):
    sub: uuid.UUID | None
    subscriptions: list[SubscriptionSchema] = []

    class Meta:
        model = User
        fields = [
            "email",
        ]


def match_redirect_domain(domain: str, url: str) -> bool:
    if domain == "*":
        return True
    pattern = domain.replace("*.", r"(?:.+\.)?")
    regex = rf"^https?://{pattern}"
    return re.match(regex, url) is not None


def validate_redirect_url(v: str | None, info: ValidationInfo) -> str:
    if not v:
        return v

    request: HttpRequest | None = info.context.get("request")
    if not request:
        return v

    client: Client | None = getattr(request, "client", None)
    if not client:
        return v

    domains = client.get_allowed_redirect_domains()

    if not domains or not any(match_redirect_domain(domain, v) for domain in domains):
        raise ValueError(f"Domain for '{v}' is not allowed")
    return v


class RedirectSchemaMixin:
    return_url: str | None = None
    cancel_url: str | None = None

    @field_validator("return_url", mode="after")
    @classmethod
    def check_return_url(cls, v: str | None, info: ValidationInfo) -> str:
        return validate_redirect_url(v, info)

    @field_validator("cancel_url", mode="after")
    @classmethod
    def check_cancel_url(cls, v: str | None, info: ValidationInfo) -> str:
        return validate_redirect_url(v, info)


class CheckoutSchema(Schema, RedirectSchemaMixin):
    plan_id: uuid.UUID
    payment_method_id: uuid.UUID


class SubscribeSchema(Schema):
    reason: str


class UpgradePlanSchema(Schema, RedirectSchemaMixin):
    to_plan_id: uuid.UUID


class LinkSchema(Schema):
    url: str


class ErrorSchema(Schema):
    message: str

class SubSchema(Schema):
    status: str
    status_update_time: str
    billing_info: str
