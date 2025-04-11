from ninja import Schema, ModelSchema, FilterSchema, Field

from payments.models import Plan


class PlanFilterSchema(FilterSchema):
    ids: list[str] | None = Field(None, q="id__in")
    is_recurring: bool | None = Field(None, q="is_recurring")


class PlanSchema(ModelSchema):
    period: str = Field(..., alias="get_period_display")

    class Meta:
        model = Plan
        fields = [
            "id",
            "name",
            "description",
            "term",
            "price",
            "is_recurring",
            "created_at",
        ]


class ErrorSchema(Schema):
    message: str
