import uuid
from ninja import Schema, ModelSchema, FilterSchema, Field

from payments.models import Plan, Processor


class ProcessorSchema(ModelSchema):

    class Meta:
        model = Processor
        fields = [
            "id",
            "type",
        ]


class PlanFilterSchema(FilterSchema):
    ids: list[uuid.UUID] | None = Field(None, q="id__in")
    is_recurring: bool | None = Field(None, q="is_recurring")


class PlanSchema(ModelSchema):
    period: str = Field(..., alias="get_period_display")
    payment_methods: list[ProcessorSchema] = Field(..., alias="get_payment_methods")

    class Meta:
        model = Plan
        fields = [
            "id",
            "name",
            "code",
            "description",
            "term",
            "price",
            "is_recurring",
            "created_at",
        ]


class ErrorSchema(Schema):
    message: str
