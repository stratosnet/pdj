import logging
import uuid
import json

from django.http import HttpRequest
from django.conf import settings
from django.db.models import Q

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
)


logger = logging.getLogger(__name__)

router = Router()


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
    q = Q(client=request.client) | Q(is_enabled=True)
    q &= filters.get_filter_expression()
    return Plan.objects.filter(q)
