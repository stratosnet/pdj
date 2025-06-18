import logging
import uuid
import json

from django.http import HttpRequest
from django.conf import settings
from django.db.models import Q, Prefetch

from ninja import Router, Header, Query
from ninja.pagination import paginate

from api.authenticators import (
    authenticate_client,
    CLIENT_ID_PARAM_NAME,
)
from .schemas import (
    PlanSchema,
    PlanFilterSchema,
    ErrorSchema,
)

from payments.models import (
    Plan,
    PlanProcessorLink,
)


logger = logging.getLogger(__name__)

router = Router(tags=["public"])


@router.get(
    "/",
    response={200: list[PlanSchema], 400: ErrorSchema},
)
@paginate
@authenticate_client(full=False)
def plans_list(
    request: HttpRequest,
    filters: PlanFilterSchema = Query(...),
    client_id: str = Header(..., alias=CLIENT_ID_PARAM_NAME),
):
    q = Q(client=request.client, is_enabled=True)
    q &= filters.get_filter_expression()
    qs = (
        Plan.objects.prefetch_related(
            Prefetch(
                "links",
                queryset=PlanProcessorLink.objects.select_related("processor").filter(
                    processor__is_enabled=True
                ),
            ),
            "plan_features__feature",
        )
        .order_by("position")
        .filter(q)
    )
    return qs
