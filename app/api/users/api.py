import logging
import uuid

from django.http import HttpRequest
from django.db import transaction
from django.db.models import Q

from ninja import Router, Header

from payments.models import Plan, PlanProcessorLink, Subscription, Invoice, Payment
from payments.clients import PaymentClient
from customizations.context import get_subscription_context

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
    SubscribeSchema,
    ChangePlanSchema,
)


logger = logging.getLogger(__name__)

router = Router(auth=[OIDCBearer(), SessionAuth(csrf=False)], tags=["public"])


@router.get(
    "/me",
    summary="Get profile info",
    response={200: MeSchema},
)
def me(request: HttpRequest):
    # TODO: Fix
    subscriptions = Subscription.objects.select_related(
        "plan", "next_billing_plan"
    ).get_user_subscriptions(request.auth.pk)
    request.auth.subscriptions.set(subscriptions)
    return request.auth


@router.post(
    "/me/subscribe",
    summary="Create subscription and return payment link",
    response={200: LinkSchema, 400: ErrorSchema},
)
@authenticate_client(full=False)
def subscribe(
    request: HttpRequest,
    data: CheckoutSchema,
    client_id: str = Header(..., alias=CLIENT_ID_PARAM_NAME),
):
    try:
        plan = Plan.objects.get(id=data.plan_id, is_enabled=True, is_recurring=True)
    except Plan.DoesNotExist:
        return 400, {"message": "Plan not found"}

    sub = Subscription.objects.latest_for_user_and_client(
        user_id=request.auth.pk, client_id=request.client.pk
    )
    if sub:
        match True:
            case sub.is_active:
                return 400, {"message": "User has active subscription"}
            case sub.is_suspended:
                return 400, {
                    "message": "Suspended subscription could be only re-subscribed"
                }

    try:
        pr = plan.links.select_related("processor").get(
            Q(
                processor_id=data.payment_method_id,
                plan__client_id=request.client.id,
            )
            & Q(external_id__isnull=False)
        )
    except PlanProcessorLink.DoesNotExist:
        return 400, {"message": "Payment method not found"}

    provider: PaymentClient = pr.processor.get_provider()

    tracking_id = Invoice.generate_tracking_id()

    # TODO: Add lock and check if subscription exist to reuse link?
    payload = provider.generate_subscription_data(
        pr.external_id,
        tracking_id,
        request.client.return_url,
        (
            request.client.cancel_url
            if request.client.cancel_url
            else request.client.return_url
        ),
    )

    if not payload or not payload.get("url"):
        return 400, {"message": "No payment link"}

    with transaction.atomic():
        invoice = Invoice.objects.create(
            id=tracking_id,
            user=request.auth,
            processor=pr.processor,
        )
        Payment.objects.create(
            invoice=invoice,
            amount=plan.price,
        )

    return {"url": payload["url"]}


@router.post(
    "/me/resubscribe",
    summary="Resume suspended subscription",
    response={204: None, 400: ErrorSchema},
)
@authenticate_client(full=False)
def resubscribe(
    request: HttpRequest,
    data: SubscribeSchema,
    client_id: str = Header(..., alias=CLIENT_ID_PARAM_NAME),
):
    try:
        sub = Subscription.objects.select_related(
            "plan", "payment", "payment__invoice", "payment__invoice__processor"
        ).latest_for_user_and_client(
            user_id=request.auth.pk, client_id=request.client.pk
        )
    except Subscription.DoesNotExist:
        return 400, {"message": "Subscription not found"}

    if not sub.plan.is_recurring:
        return 400, {"message": "Subscription on non recurring plan"}

    if not sub.is_suspended:
        return 400, {"message": "Subscription is active"}

    if not sub.payment_id:
        return 400, {
            "message": "Subscription without payment could not be changed, cancled or re-subscribed"
        }

    provider: PaymentClient = sub.payment.invoice.processor.get_provider()
    provider.activate_subscription(
        sub.payment.invoice.external_id,
        data.reason,
    )

    return 204, None


@router.post(
    "/me/unsubscribe",
    summary="Unsubscribe from current subscription",
    response={204: None, 400: ErrorSchema},
)
@authenticate_client(full=False)
def unsubscribe(
    request: HttpRequest,
    data: SubscribeSchema,
    client_id: str = Header(..., alias=CLIENT_ID_PARAM_NAME),
):
    try:
        sub = Subscription.objects.select_related(
            "plan", "payment", "payment__invoice", "payment__invoice__processor"
        ).latest_for_user_and_client(
            user_id=request.auth.pk, client_id=request.client.pk
        )
    except Subscription.DoesNotExist:
        return 400, {"message": "Subscription not found"}

    if not sub.plan.is_recurring:
        return 400, {"message": "Subscription on non recurring plan"}

    if not sub.is_active or not sub.next_billing_at:
        return 400, {"message": "Subscription has been unsubscribed"}

    if not sub.payment_id:
        return 400, {
            "message": "Subscription without payment could not be changed, cancled or re-subscribed"
        }

    provider: PaymentClient = sub.payment.invoice.processor.get_provider()
    provider.deactivate_subscription(
        sub.payment.invoice.external_id,
        data.reason,
        suspend=True,  # TODO: Add flag to processor model
    )

    return 204, None


@router.post(
    "/me/changeplan",
    summary="Upgrade/downgrade current plan and return payment link",
    response={200: LinkSchema, 400: ErrorSchema},
)
@authenticate_client(full=False)
def change_plan(
    request: HttpRequest,
    data: ChangePlanSchema,
    client_id: str = Header(..., alias=CLIENT_ID_PARAM_NAME),
):
    try:
        sub = Subscription.objects.select_related(
            "plan", "payment", "payment__invoice", "payment__invoice__processor"
        ).latest_for_user_and_client(
            user_id=request.auth.pk, client_id=request.client.pk
        )
    except Subscription.DoesNotExist:
        return 400, {"message": "Subscription not found"}

    if not sub.plan.is_recurring:
        return 400, {"message": "Subscription on non recurring plan"}

    if not sub.is_active or not sub.next_billing_at:
        return 400, {"message": "Subscription has been unsubscribed"}

    if not sub.payment_id:
        return 400, {
            "message": "Subscription without payment could not be changed, cancled or re-subscribed"
        }

    try:
        plan = Plan.objects.get(id=data.to_plan_id)
    except Plan.DoesNotExist:
        return 400, {"message": "Plan not found"}

    if plan.id == sub.plan.id or (
        sub.next_billing_plan_id and plan.id == sub.next_billing_plan_id
    ):
        return 400, {"message": "Switch could be only on a different plan"}

    # NOTE: If another provider will be added, we should add more logic here to create a correct switch
    # or user always same provider
    proc_ref = plan.links.filter(processor=sub.invoice.processor).first()

    provider: PaymentClient = sub.payment.invoice.processor.get_provider()
    payload = provider.generate_change_subscription_data(
        sub.payment.invoice.external_id,
        proc_ref.external_id,
        request.client.return_url,
        (
            request.client.cancel_url
            if request.client.cancel_url
            else request.client.return_url
        ),
    )
    if not payload or not payload.get("url"):
        return 400, {"message": "Subscription could not be changed"}

    return 200, {"url": payload["url"]}
