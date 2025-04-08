from ninja import Schema, ModelSchema, FilterSchema, Field

from ..plans.schemas import PlanSchema
from accounts.models import SSOUser
from payments.models import Subscription


class UserSchema(ModelSchema):
    class Meta:
        model = SSOUser
        fields = [
            "sub",
        ]


class SubscriptionFilterSchema(FilterSchema):
    ids: list[str] | None = Field(None, q="id__in")
    user_id: list[str] | None = Field(None, q="user_id")
    is_recurring: bool | None = Field(None, q="plan__is_recurring")


class SubscriptionSchema(ModelSchema):
    user: UserSchema
    plan: PlanSchema
    # order

    class Meta:
        model = Subscription
        fields = [
            "id",
            # "is_active",
            "start_at",
            "end_at",
            "created_at",
        ]


class ErrorSchema(Schema):
    message: str
