import logging
import uuid

from django.http import HttpRequest
from django.conf import settings
from django.db import transaction
from django.db.models import Q

from ninja import Router, Header

from payments.models import Plan, PlanProcessorLink, Subscription, Payment
from payments.clients import PaymentClient

from ..authenticators import (
    OIDCBearer,
    authenticate_client,
    CLIENT_ID_PARAM_NAME,
)
from .schemas import (
    MeSchema,
    LinkSchema,
    CheckoutSchema,
    ErrorSchema,
    SubscriptionChangeSchema,
)


logger = logging.getLogger(__name__)

router = Router(
    auth=OIDCBearer(),
)


@router.get(
    "/me",
    summary="Get profile info",
    response={200: MeSchema},
)
def me(request: HttpRequest):
    subscriptions = Subscription.objects.select_related("plan").get_user_subscriptions(
        request.sso.pk
    )
    request.sso.subscriptions.set(subscriptions)
    return request.sso


@router.post(
    "/checkout",
    summary="Get payment link",
    response={200: LinkSchema, 400: ErrorSchema},
)
@authenticate_client(full=False)
def checkout(
    request: HttpRequest,
    data: CheckoutSchema,
    client_id: str = Header(..., alias=CLIENT_ID_PARAM_NAME),
):
    try:
        plan = Plan.objects.get(id=data.plan_id, is_enabled=True)
    except Plan.DoesNotExist:
        return 400, {"message": "Plan not found"}

    try:
        pr = plan.links.select_related("processor").get(
            Q(
                plan_id=plan.id,
                processor_id=data.payment_method_id,
                plan__client_id=request.client.id,
            )
            & Q(external_id__isnull=False)
        )
    except PlanProcessorLink.DoesNotExist:
        return 400, {"message": "Payment method not found"}

    provider: PaymentClient = pr.processor.get_provider()

    # TODO: Add non reccuring
    if not plan.is_recurring:
        return 400, {"message": "Non recurring plan not supported yet"}

    tracking_id = uuid.uuid4().hex

    payload = provider.generate_subscription_data(
        pr.external_id,
        tracking_id,
        request.client.home_url,  # TODO: Add return and cancel url
        request.client.home_url,
    )

    print("payload", payload)

    if not payload or not payload.get("url"):
        return 400, {"message": "No payment link"}

    Payment.objects.create(
        id=tracking_id,
        external_id=payload["id"],
        user=request.sso,
        processor=pr.processor,
        amount=plan.price,
    )

    return {"url": payload["url"]}


# TODO: ID????
@router.delete(
    "/subscriptions/{id}",
    response={400: ErrorSchema},
)
def subscriptions_cancel(
    request: HttpRequest,
    id: int,
    data: SubscriptionChangeSchema,
):
    try:
        sub = Subscription.objects.select_related(
            "payment", "payment__processor"
        ).get_active_last(user_id=request.sso.id)
    except Subscription.DoesNotExist:
        return 400, {"message": "Subscription not found"}

    if sub.external_id:
        provider: PaymentClient = sub.payment.processor.get_provider()

        # NOTE: Move to celery?
        unsubscribed = provider.cancel_subscription(
            sub.external_id,
            data.reason,
        )

    sub.end_at = sub.start_at
    sub.save(update_fields=["end_at"])

    return 204, None


@router.put(
    "/subscriptions/{id}",
    response={400: ErrorSchema},
)
def subscriptions_switch(
    request: HttpRequest,
    id: int,
    data: SubscriptionChangeSchema,
):
    # TODO
    return 204, None
