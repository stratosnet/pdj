import logging
import uuid

from django.http import HttpRequest
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.db.models import Q

from ninja import Router, Header

from payments.models import Plan, PlanProcessorLink, Subscription, Payment
from payments.clients import PaymentClient

from ..authenticators import (
    OIDCBearer,
    SessionAuth,
    authenticate_client,
    CLIENT_ID_PARAM_NAME,
)
from .schemas import (
    MeSchema,
    LinkSchema,
    CheckoutSchema,
    ErrorSchema,
    SubscriptionCancelSchema,
    SubscriptionSwitchSchema,
)


logger = logging.getLogger(__name__)

router = Router(
    auth=[OIDCBearer()],
)


@router.get(
    "/me",
    summary="Get profile info",
    response={200: MeSchema},
)
def me(request: HttpRequest):
    print("request.auth", request.auth)
    subscriptions = Subscription.objects.select_related("plan").get_user_subscriptions(
        request.auth.pk
    )
    request.auth.subscriptions.set(subscriptions)
    return request.auth


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
        user=request.auth,
        processor=pr.processor,
        amount=plan.price,
    )

    return {"url": payload["url"]}


@router.post(
    "/subscriptions/{id}",
    response={204: None, 400: ErrorSchema},
)
def subscriptions_cancel(
    request: HttpRequest,
    id: int,
    data: SubscriptionCancelSchema,
):
    try:
        sub = Subscription.objects.select_related(
            "plan", "payment", "payment__processor"
        ).get(id=id, user_id=request.auth.pk)
    except Subscription.DoesNotExist:
        return 400, {"message": "Subscription not found"}

    if not sub.plan.is_recurring:
        return 400, {"message": "Subscription could not be canceled"}

    if not sub.is_active:
        return 400, {"message": "Subscription has been expired"}

    if not sub.next_billing_at:
        return 400, {"message": "Subscription has been canceled"}

    if not sub.payment or not sub.payment.external_id:
        return 400, {"message": "Subscription could not be canceled"}

    provider: PaymentClient = sub.payment.processor.get_provider()
    provider.cancel_subscription(
        sub.payment.external_id,
        data.reason,
    )

    sub.end_at = sub.next_billing_at
    sub.next_billing_at = None
    sub.save(update_fields=["end_at", "next_billing_at"])

    return 204, None


@router.put(
    "/subscriptions/{id}",
    response={200: LinkSchema, 400: ErrorSchema},
)
def subscriptions_switch(
    request: HttpRequest,
    id: int,
    data: SubscriptionSwitchSchema,
):
    try:
        sub = Subscription.objects.select_related(
            "plan", "payment", "payment__processor"
        ).get(id=id, user_id=request.auth.pk)
    except Subscription.DoesNotExist:
        return 400, {"message": "Subscription not found"}

    if not sub.is_active:
        return 400, {"message": "Subscription has been expired"}

    if not sub.next_billing_at:
        return 400, {"message": "Subscription has been canceled"}

    if not sub.payment or not sub.payment.external_id:
        return 400, {"message": "Subscription could not be canceled"}

    try:
        plan = Plan.objects.get(id=data.to_plan_id)
    except Plan.DoesNotExist:
        return 400, {"message": "Plan not found"}

    if plan.id == sub.plan.id:
        return 400, {"message": "Switch could be only on a different plan"}

    # NOTE: If another provider will be added, we should add more logic here to create a correct switch
    # or user always same provider
    proc_ref = plan.links.filter(processor=sub.payment.processor).first()

    provider: PaymentClient = sub.payment.processor.get_provider()
    payload = provider.generate_change_subscription_data(
        sub.payment.external_id, proc_ref.external_id
    )
    if not payload or not payload.get("url"):
        return 400, {"message": "Subscription could not be changed"}

    return 200, {"url": payload["url"]}
