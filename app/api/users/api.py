import logging

from django.http import HttpRequest
from django.db import transaction
from django.db.models import Q

from ninja import Router, Header

from payments.models import (
    Plan,
    PlanProcessorLink,
    Processor,
    Subscription,
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
    UpgradePlanSchema,
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
    ).get_user_subscriptions(request.auth.pk)

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
        )
    except PlanProcessorLink.DoesNotExist:
        return 400, {"message": "Payment method not found"}

    if plan.is_recurring and not pr.external_id:
        return 400, {"message": "Payment method not found"}

    processor: Processor = pr.processor

    custom_id = ProcessorIDSerializer.serialize_subscription()

    def create_url():
        if plan.is_recurring:
            url = processor.create_subscription_url(
                custom_id,
                pr.external_id,
                data.return_url,
                (data.cancel_url if data.cancel_url else data.return_url),
            )
        else:
            url = processor.create_checkout_url(
                custom_id,
                plan.price,
                data.return_url,
                (data.cancel_url if data.cancel_url else data.return_url),
            )
        return url

    # cache_key = ProcessorIDSerializer.get_cache_key(
    #     "subscribe", plan.id, processor.id, request.auth.id
    # )
    # url = ProcessorIDSerializer.get_or_create_url(cache_key, create_url)
    url = create_url()
    if not url:
        return 400, {"message": "No payment link"}

    _, subscription_id = ProcessorIDSerializer.deserialize(custom_id)
    with transaction.atomic():
        print(f"{sub=}")
        if sub and sub.is_null:
            # Delete the old null subscription and create a new one with the correct id
            sub.delete()
        Subscription.objects.create(
            id=subscription_id,
            user=request.auth,
            plan=plan,
            active_processor=processor,
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
    )

    return 204, None


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

    processor: Processor = sub.active_processor

    # NOTE: If another provider will be added, we should add more logic here to create a correct switch
    # or user always same provider
    proc_ref = next_plan.links.filter(processor=processor).first()
    if not proc_ref or not proc_ref.external_id:
        return 400, {"message": "Payment method for new plan not found"}

    def create_url():
        return processor.create_change_plan_url(
            sub.external_id,
            proc_ref.external_id,
            data.return_url,
            (data.cancel_url if data.cancel_url else data.return_url),
        )

    # cache_key = ProcessorIDSerializer.get_cache_key(
    #     "changeplan", next_plan.id, processor.id, request.auth.id
    # )

    # url = ProcessorIDSerializer.get_or_create_url(cache_key, create_url)
    url = create_url()
    if not url:
        return 400, {"message": "Subscription could not be changed"}

    return 200, {"url": url}
