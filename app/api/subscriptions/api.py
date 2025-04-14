import logging

from django.http import HttpRequest
from django.conf import settings
from django.db.models import Q
from django.db.models import Prefetch

from ninja import Router, Header, Query
from ninja.pagination import paginate

from ..authenticators import (
    authenticate_client,
    CLIENT_ID_PARAM_NAME,
    CLIENT_SECRET_PARAM_NAME,
)
from .schemas import (
    SubscriptionSchema,
    SubscriptionFilterSchema,
    ErrorSchema,
)

from payments.models import (
    Subscription,
)


logger = logging.getLogger(__name__)

router = Router()


@router.get(
    "/",
    response={200: list[SubscriptionSchema], 400: ErrorSchema},
)
@paginate
@authenticate_client
def subscriptions_list(
    request: HttpRequest,
    filters: SubscriptionFilterSchema = Query(...),
    client_id: str = Header(..., alias=CLIENT_ID_PARAM_NAME),
    client_secret: str = Header(..., alias=CLIENT_SECRET_PARAM_NAME),
):
    q = Q(plan__client=request.client, plan__is_enabled=True)
    q &= filters.get_filter_expression()
    qs = (
        Subscription.objects.select_related("user", "plan")
        .prefetch_related("user__sso_identities")
        .filter(q)
    )
    return qs
