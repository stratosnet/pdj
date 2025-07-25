import logging

from django.http import HttpRequest
from django.db import transaction
from django.db.models import Q
from django.utils.dateparse import parse_datetime
from django.utils import timezone

import time
import json

from ninja import Router, Header

from payments.models import (
    Plan,
    PlanProcessorLink,
    Processor,
    Subscription,
    PaymentUrlCache,
)

from payments.signals import (
    subscription_suspend,
    subscription_activate,
)
from payments.serializers import ProcessorIDSerializer
from core.utils import (
    validate_schema_with_context,
)

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
    UpgradePlanSchema, SubSchema,
)


logger = logging.getLogger(__name__)

router = Router(auth=[OIDCBearer(), SessionAuth(csrf=False)], tags=["public"])


@router.get(
    "/me",
    summary="Get profile info",
    response={200: MeSchema},
)
def me(request: HttpRequest):
    subscriptions = Subscription.objects.select_related(
        "plan", "next_billing_plan"
    ).get_user_subscriptions_gt_next_billing_at(request.auth.pk)

    return {
        "email": request.auth.email,
        "sub": request.auth.sub,
        "subscriptions": subscriptions,
    }


@router.post(
    "/me/upgrade",
    summary="Request for upgrade of active subscription (not implemented)",
    include_in_schema=False,
    response={200: LinkSchema, 400: ErrorSchema},
)
@authenticate_client(full=False)
def me_upgrade(
    request: HttpRequest,
    data: UpgradePlanSchema,
    client_id: str = Header(..., alias=CLIENT_ID_PARAM_NAME),
):
    data = validate_schema_with_context(router.api, request, UpgradePlanSchema, data)

    sub = Subscription.objects.select_related(
        "plan",
        "active_processor",
        "next_billing_plan",
    ).latest_for_user_and_client(user_id=request.auth.pk, client_id=request.client.pk)
    if not sub:
        return 400, {"message": "Subscription not found"}

    if sub.is_expired:
        return 400, {"message": "Subscription is expired"}

    if sub.is_suspended:
        return 400, {"message": "Subscription is suspended"}

    if not sub.external_id:
        return 400, {
            "message": "Subscription without payment could not be changed, cancled or re-subscribed"
        }

    if sub.plan.is_recurring and not sub.next_billing_plan_id:
        return 400, {"message": "Re-curring subscription should first to change a plan"}

    try:
        next_plan = Plan.objects.get(id=data.to_plan_id)
    except Plan.DoesNotExist:
        return 400, {"message": "Plan not found"}

    if next_plan.id == sub.plan.id or (
        sub.next_billing_plan_id and next_plan.id == sub.next_billing_plan_id
    ):
        return 400, {"message": "Upgrade could be only on a different plan"}

    custom_id = ProcessorIDSerializer.serialize_plan_upgrade()

    amount = sub.calculate_upgrade_amount(next_plan)
    if amount == 0:
        return 400, {"message": "Upgrade could be only on plan higher"}

    # TODO: As not impelented, cache should be add later as possibility of
    # structural changes
    url = sub.active_processor.create_checkout_url(
        custom_id,
        amount,
        # TODO: Add arg to path for action upgrade
        data.return_url,
        (data.cancel_url if data.cancel_url else data.return_url),
    )

    if not url:
        return 400, {"message": "No payment link"}

    return 200, {"url": url}


@router.post(
    "/me/subscribe",
    summary="Request for subscription and return payment link to activate",
    response={200: LinkSchema, 400: ErrorSchema},
)
@authenticate_client(full=False)
def me_subscribe(
    request: HttpRequest,
    data: CheckoutSchema,
    client_id: str = Header(..., alias=CLIENT_ID_PARAM_NAME),
):
    data = validate_schema_with_context(router.api, request, CheckoutSchema, data)

    try:
        plan = Plan.objects.get(id=data.plan_id, is_enabled=True, client=request.client)
    except Plan.DoesNotExist:
        return 400, {"message": "Plan not found"}

    sub = Subscription.objects.latest_for_user_and_client(
        user_id=request.auth.pk,
        client_id=request.client.pk,
        include_uninitialized=True,
    )
    next_billing_at = None
    if sub:
        if sub.next_billing_at:
           next_billing_at = sub.next_billing_at
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
        )
    except PlanProcessorLink.DoesNotExist:
        return 400, {"message": "Payment method not found"}

    if plan.is_recurring and not pr.external_id:
        return 400, {"message": "Payment method not found"}

    processor: Processor = pr.processor

    if sub:
        url = PaymentUrlCache.objects.get_subscription_cache_url(
            subscription_id=sub.pk,
            processor_id=processor.pk,
        )
        if url:
            return {"url": url}

    custom_id = ProcessorIDSerializer.serialize_subscription()

    start_time = None
    if plan.is_recurring:
        if next_billing_at:
            start_time = next_billing_at
        url = processor.create_subscription_url(
            custom_id,
            pr.external_id,
            data.return_url,
            (data.cancel_url if data.cancel_url else data.return_url),
            start_time=start_time
        )
    else:
        url = processor.create_checkout_url(
            custom_id,
            plan.price,
            data.return_url,
            (data.cancel_url if data.cancel_url else data.return_url),
        )
    if not url:
        return 400, {"message": "No payment link"}

    _, subscription_id = ProcessorIDSerializer.deserialize(custom_id)
    with transaction.atomic():
        sub = Subscription.objects.create(
            id=subscription_id,
            user=request.auth,
            plan=plan,
            active_processor=processor,
        )
        PaymentUrlCache.objects.create_subscription_cache(
            subscription_id=sub.pk,
            processor_id=processor.pk,
            url=url,
        )

    return {"url": url}


@router.post(
    "/me/resubscribe",
    summary="Resume suspended subscription",
    response={204: None, 400: ErrorSchema},
)
@authenticate_client(full=False)
def me_resubscribe(
    request: HttpRequest,
    data: SubscribeSchema,
    client_id: str = Header(..., alias=CLIENT_ID_PARAM_NAME),
):
    sub = Subscription.objects.select_related(
        "plan", "active_processor"
    ).latest_for_user_and_client(user_id=request.auth.pk, client_id=request.client.pk)
    if not sub:
        return 400, {"message": "Subscription not found"}

    if not sub.plan.is_recurring:
        return 400, {"message": "Subscription on non recurring plan"}

    if not sub.is_suspended:
        return 400, {"message": "Subscription is active"}

    if not sub.external_id:
        return 400, {
            "message": "Subscription without payment could not be changed, cancled or re-subscribed"
        }

    processor: Processor = sub.active_processor
    processor.activate_subscription(
        sub.external_id,
        data.reason,
    )

    return 204, None


@router.post(
    "/me/unsubscribe",
    summary="Unsubscribe from current subscription",
    response={204: None, 400: ErrorSchema},
)
@authenticate_client(full=False)
def me_unsubscribe(
    request: HttpRequest,
    data: SubscribeSchema,
    client_id: str = Header(..., alias=CLIENT_ID_PARAM_NAME),
):
    sub = Subscription.objects.select_related(
        "plan", "active_processor"
    ).latest_for_user_and_client(user_id=request.auth.pk, client_id=request.client.pk)
    if not sub:
        return 400, {"message": "Subscription not found"}

    if not sub.plan.is_recurring:
        return 400, {"message": "Subscription on non recurring plan"}

    if not sub.is_active or not sub.next_billing_at:
        return 400, {"message": "Subscription has been unsubscribed"}

    if not sub.external_id:
        return 400, {
            "message": "Subscription without payment could not be changed, cancled or re-subscribed"
        }

    processor: Processor = sub.active_processor
    processor.deactivate_subscription(
        sub.external_id,
        data.reason,
        False if data.reason == "cancelsubscribe" else True
    )

    return 204, None

@router.post(
    "/me/subscription",
    summary="show detail subscription",
    response={200: SubSchema, 400: ErrorSchema},
)
@authenticate_client(full=False)
def me_show_subscription(
    request: HttpRequest,
    data: SubscribeSchema,
    client_id: str = Header(..., alias=CLIENT_ID_PARAM_NAME),
):
    sub = Subscription.objects.select_related(
        "plan", "active_processor"
    ).latest_for_user_and_client(user_id=request.auth.pk, client_id=request.client.pk)
    if not sub:
        return 400, {"message": "Subscription not found"}
    if not sub.external_id:
        return 400, {
            "message": "Subscription without payment could not be changed, cancled or re-subscribed"
        }
    processor: Processor = sub.active_processor
    rsub = processor.get_subscription_details(sub.external_id)
    # rsub_transactions = processor.list_transactions_for_subscription(sub.external_id)
    status = rsub["status"]
    if not sub.is_suspended and status == "SUSPENDED":
        suspended_at = parse_datetime(
            rsub["status_update_time"]
        )
        subscription_suspend.send(
            sender=None,
            subscription_id=sub.id,
            suspended_at=suspended_at,
        )
    if  sub.is_suspended and status == "ACTIVE":

        #  external_invoice_id = webhook_event["resource"]["id"]
        # _, subscription_id = ProcessorIDSerializer.deserialize(
        #         webhook_event["resource"]["custom_id"]
        #     )
        # external_plan_id = webhook_event["resource"]["plan_id"]
        # last_payment = webhook_event["resource"]["billing_info"]["last_payment"]
        # amount = Decimal(last_payment["amount"]["value"])
        # currency = last_payment["amount"]["currency_code"]
        # start_at = parse_datetime(webhook_event["resource"]["start_time"])
        # end_at = parse_datetime(
        #         webhook_event["resource"]["billing_info"]["next_billing_time"]
        #     )
        amount = rsub["billing_info"]["last_payment"]["amount"]["value"]
        currency = rsub["billing_info"]["last_payment"]["amount"]["currency_code"]

        start_at = rsub["start_time"]
        # end_at=>next_billing_date
        end_at = rsub["billing_info"]["next_billing_time"]

        external_invoice_id = rsub["id"]
        external_plan_id = rsub["plan_id"]
        subscription_id = sub.id

        subscription_activate.send(
            sender=None,
            external_invoice_id=external_invoice_id,
            external_plan_id=external_plan_id,
            subscription_id=subscription_id,
            amount=amount,
            currency=currency,
            start_at=start_at,
            end_at=end_at,
        )
        # print("return: ", status, suspended_at)
    billing_info= {
        "sub.status": status,
        "sub.external_id": sub.external_id,
        "sub.id": str(sub.id),
        "rsub": rsub["billing_info"]
    }
    return 200, {"status": rsub["status"], "status_update_time": rsub["status_update_time"], "billing_info": json.dumps(billing_info)}

@router.post(
    "/me/changeplan",
    summary="Upgrade/downgrade current plan and return payment link",
    response={200: LinkSchema, 400: ErrorSchema},
)
@authenticate_client(full=False)
def me_change_plan(
    request: HttpRequest,
    data: UpgradePlanSchema,
    client_id: str = Header(..., alias=CLIENT_ID_PARAM_NAME),
):
    data = validate_schema_with_context(router.api, request, UpgradePlanSchema, data)

    sub = Subscription.objects.select_related(
        "plan", "active_processor"
    ).latest_for_user_and_client(user_id=request.auth.pk, client_id=request.client.pk)
    if not sub:
        return 400, {"message": "Subscription not found"}

    if not sub.plan.is_recurring:
        return 400, {"message": "Subscription on non recurring plan"}

    if not sub.is_active or not sub.next_billing_at:
        return 400, {"message": "Subscription has been unsubscribed"}

    if not sub.external_id:
        return 400, {
            "message": "Subscription without payment could not be changed, cancled or re-subscribed"
        }

    try:
        next_plan = Plan.objects.get(id=data.to_plan_id)
    except Plan.DoesNotExist:
        return 400, {"message": "Plan not found"}

    if next_plan.id == sub.plan.id or (
        sub.next_billing_plan_id and next_plan.id == sub.next_billing_plan_id
    ):
        return 400, {"message": "Switch could be only on a different plan"}

    if next_plan.is_default:
        return 400, {"message": "Default plan could not be used for switch"}

    processor: Processor = sub.active_processor

    # NOTE: If another provider will be added, we should add more logic here to create a correct switch
    # or user always same provider
    proc_ref = next_plan.links.filter(processor=processor).first()
    if not proc_ref or not proc_ref.external_id:
        return 400, {"message": "Payment method for new plan not found"}

    url = PaymentUrlCache.objects.get_change_plan_cache_url(
        subscription_id=sub.pk,
        plan_id=next_plan.pk,
        processor_id=processor.pk,
    )
    if url:
        return {"url": url}

    url = processor.create_change_plan_url(
        sub.external_id,
        proc_ref.external_id,
        data.return_url,
        (data.cancel_url if data.cancel_url else data.return_url),
    )
    if not url:
        return 400, {"message": "Subscription could not be changed"}

    PaymentUrlCache.objects.create_change_plan_cache(
        subscription_id=sub.pk,
        plan_id=next_plan.pk,
        processor_id=processor.pk,
        url=url,
    )

    return 200, {"url": url}
