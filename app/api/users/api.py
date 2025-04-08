import logging
import uuid

from django.http import HttpRequest
from django.conf import settings

from ninja import Router

from payments.models import Subscription
from payments.clients import PaymentClient

from ..authenticators import (
    OIDCBearer,
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
    from payments.models import Subscription

    subscriptions = Subscription.objects.get_user_subscriptions(request.sso.pk)
    request.sso.subscriptions.set(subscriptions)
    return request.sso


@router.post(
    "/checkout",
    summary="Get payment link",
    response={200: LinkSchema, 400: ErrorSchema},
)
def checkout(request: HttpRequest, data: CheckoutSchema):
    from payments.models import Plan, PaymentReference
    from payments.clients import PaymentClient

    try:
        plan = Plan.objects.get(id=data.plan_id, is_enabled=True)
    except Plan.DoesNotExist:
        return 400, {"message": "Plan not found"}

    try:
        pr = PaymentReference.objects.select_related("processor").get(
            processor=data.payment_method_id, object_id=plan.id
        )
    except PaymentReference.DoesNotExist:
        return 400, {"message": "Payment method not found"}

    provider: PaymentClient = pr.processor.get_provider()

    url = None  # TODO: Add non reccuring
    if plan.is_recurring:
        url = provider.generate_subscription_link(
            pr.external_id,
            uuid.uuid4().hex,  # TODO: Add order
            request.client.home_url,  # TODO: Add return and cancel url
            request.client.home_url,
        )

    if not url:
        return 400, {"message": "No payment link"}

    print("url", url)

    return {"url": url}


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
        sub = Subscription.objects.get_active_last(id=id)
    except Subscription.DoesNotExist:
        return 400, {"message": "Subscription not found"}

    pr = sub.links.first()
    if not pr:
        return 400, {"message": "Payment method not found"}

    provider: PaymentClient = pr.processor.get_provider()

    # NOTE: Move to celery?
    unsubscribed = provider.cancel_subscription(
        pr.external_id,
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
