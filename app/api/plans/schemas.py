import uuid
from ninja import Schema, ModelSchema, FilterSchema, Field

from payments.models import Plan, Feature, PlanFeature, Processor


class ProcessorSchema(ModelSchema):

    class Meta:
        model = Processor
        fields = [
            "id",
            "type",
        ]


class PlanFeatureSchema(ModelSchema):
    id: uuid.UUID = Field(...)
    key: str = Field(..., alias="feature.key")
    name: str = Field(..., alias="feature.name")
    description: str = Field(..., alias="feature.description")

    class Meta:
        model = PlanFeature
        fields = [
            "value",
        ]


class PlanFilterSchema(FilterSchema):
    ids: list[uuid.UUID] | None = Field(None, q="id__in")
    is_recurring: bool | None = Field(None, q="is_recurring")


class PlanSchema(ModelSchema):
    period: str = Field(..., alias="get_period_display")
    payment_methods: list[ProcessorSchema] = Field(..., alias="get_payment_methods")
    features: list[PlanFeatureSchema] = Field(..., alias="plan_features")

    class Meta:
        model = Plan
        fields = [
            "id",
            "name",
            "code",
            "position",
            "description",
            "term",
            "price",
            "is_recurring",
        ]


class ErrorSchema(Schema):
    message: str
