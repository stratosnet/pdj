import uuid
from ninja import Schema, ModelSchema

from accounts.models import User
from payments.models import Subscription


class SubscriptionSchema(ModelSchema):
    plan_id: uuid.UUID
    is_active: bool

    class Meta:
        model = Subscription
        fields = [
            "id",
            "start_at",
            "end_at",
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


class CheckoutSchema(Schema):
    plan_id: uuid.UUID
    payment_method_id: uuid.UUID


class SubscriptionCancelSchema(Schema):
    reason: str


class SubscriptionSwitchSchema(Schema):
    to_plan_id: uuid.UUID


class LinkSchema(Schema):
    url: str


class ErrorSchema(Schema):
    message: str
