from ninja import Schema, ModelSchema

from accounts.models import SSOUser
from payments.models import Subscription


class SubscriptionSchema(ModelSchema):
    plan_id: int
    is_active: bool

    class Meta:
        model = Subscription
        fields = [
            "id",
            "start_at",
            "end_at",
            "created_at",
        ]


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
