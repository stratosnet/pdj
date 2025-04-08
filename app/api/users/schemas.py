from ninja import Schema, ModelSchema

from accounts.models import SSOUser
from ..subscriptions.schemas import SubscriptionSchema


class MeSchema(ModelSchema):
    subscriptions: list[SubscriptionSchema] = []

    class Meta:
        model = SSOUser
        fields = [
            "sub",
        ]


class CheckoutSchema(Schema):
    plan_id: int
    payment_method_id: int


class SubscriptionChangeSchema(Schema):
    reason: str


class LinkSchema(Schema):
    url: str


class ErrorSchema(Schema):
    message: str
