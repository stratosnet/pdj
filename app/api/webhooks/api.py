import logging
import json
from decimal import Decimal
from datetime import datetime

from django.db import transaction
from django.utils import timezone
from django.http import HttpRequest
from django.conf import settings
from django.utils.dateparse import parse_datetime

from ninja import Router

from payments.models import (
    Processor,
    Subscription,
    Plan,
    Payment,
)
from payments.clients import PayPalClient
from .schemas import (
    PayPalWebhookSchema,
    ErrorSchema,
)
from .exceptions import (
    PaymentException,
    PaymentNotFound,
    PaymentWrongStatus,
    SubscriptionNotFound,
)


logger = logging.getLogger(__name__)

router = Router()


@router.post(
    "/{webhook_secret}/paypal",
    include_in_schema=False,
    auth=None,
    response={200: ErrorSchema, 204: None, 400: ErrorSchema, 500: ErrorSchema},
)
def webhook_paypal(
    request: HttpRequest,
    webhook_secret: str,
):
    auth_algo = request.headers.get("PAYPAL-AUTH-ALGO")
    cert_url = request.headers.get("PAYPAL-CERT-URL")
    transmission_id = request.headers.get("PAYPAL-TRANSMISSION-ID")
    transmission_sig = request.headers.get("PAYPAL-TRANSMISSION-SIG")
    transmission_time = request.headers.get("PAYPAL-TRANSMISSION-TIME")

    try:
        processor = Processor.objects.get(webhook_secret=webhook_secret)
    except Processor.DoesNotExist:
        return 400, {"message": "Processor not set"}

    provider: PayPalClient = processor.get_provider()

    webhook_data = request.body.decode("utf-8")
    logger.info("webhook_event: %s", webhook_data)

    webhook_event = json.loads(webhook_data)

    resp = provider.verify_webhook_signature(
        {
            "auth_algo": auth_algo,
            "cert_url": cert_url,
            "transmission_id": transmission_id,
            "transmission_sig": transmission_sig,
            "transmission_time": transmission_time,
        },
        processor.endpoint_secret,
        json.loads(webhook_data),
    )

    status = resp.get("verification_status")
    if status != "SUCCESS":
        logger.warning(
            f"PayPal webhook status verification failed for '{webhook_secret}'"
        )
        return 400, {"message": "Verification failed"}

    try:
        match webhook_event["event_type"]:
            case "PAYMENT.SALE.COMPLETED":
                external_id = webhook_event["resource"]["billing_agreement_id"]
                amount = Decimal(webhook_event["resource"]["amount"]["total"])
                currency = webhook_event["resource"]["amount"]["currency"]
                on_payment_completed(external_id, amount, currency)
            case "BILLING.SUBSCRIPTION.ACTIVATED":
                external_id = webhook_event["resource"]["id"]
                plan_id = webhook_event["resource"]["plan_id"]
                last_payment = webhook_event["resource"]["billing_info"]["last_payment"]
                amount = Decimal(last_payment["amount"]["value"])
                currency = last_payment["amount"]["currency_code"]
                start_at = parse_datetime(webhook_event["resource"]["start_time"])
                end_at = parse_datetime(
                    webhook_event["resource"]["billing_info"]["next_billing_time"]
                )
                on_subscription_create(
                    plan_id, external_id, amount, currency, start_at, end_at
                )
            case _:
                logger.warning(
                    f"Not supported event type: {webhook_event['event_type']}"
                )
                return 200, {"message": "Event match not supported"}
    except PaymentException as e:
        logger.warning(f"Payment error: {e.args}")
        return 400, {"message": f"Webhook error: {e.args}"}
    except Exception as e:
        logger.exception(e)
        return 500, {"message": "Unhandled error"}

    return 204, None


@transaction.atomic
def on_payment_completed(external_id: str, amount: Decimal, currency: str):
    last_payment = (
        Payment.objects.select_related("user", "processor", "subscription__plan")
        .filter(external_id=external_id)
        .first()
    )
    if not last_payment or not last_payment.subscription:
        raise PaymentNotFound(f"Last payment for external id '{external_id}' not found")

    payment = Payment.objects.create(
        external_id=external_id,
        user=last_payment.user,
        processor=last_payment.processor,
        amount=amount,
        currency=currency,
        status=Payment.SUCCESS,
    )

    now = timezone.now()

    sub = Subscription.objects.get_active_last(
        plan_id=last_payment.subscription.plan.pk, user_id=payment.user.pk
    )
    if not sub:
        raise SubscriptionNotFound(
            "Subscription does not exist to perform recurring payment"
        )

    sub.end_at = now
    sub.update(update_fields=["end_at"])

    sub = Subscription.objects.create(
        user=payment.user,
        plan=sub.plan,
        payment=payment,
        start_at=now,  # TODO: Maybe to get from create time?
    )
    sub.update_end_date()
    sub.save(update_fields=["end_at"])


@transaction.atomic
def on_subscription_create(
    plan_id: str,
    external_id: str,
    amount: str,
    currency: str,
    start_at: datetime,
    end_at: datetime | None,
):
    payment = (
        Payment.objects.select_related("user").filter(external_id=external_id).first()
    )
    if payment:
        if payment.status != Payment.PENDING:
            raise PaymentWrongStatus(
                f"Payment for external id '{external_id}' has wrong status (got: {payment.status}, should be: {Payment.PENDING})"
            )
        else:
            payment.status = Payment.SUCCESS
            payment.amount = amount
            payment.currency = currency
            payment.save(update_fields=["status", "amount", "currency"])
    else:
        raise PaymentNotFound(f"Last payment for external id '{external_id}' not found")

    plan = Plan.objects.filter(links__external_id=plan_id).first()
    sub = Subscription.objects.get_active_last(plan_id=plan.pk, user_id=payment.user.pk)
    if sub:
        sub.end_at = start_at
        sub.update(update_fields=["end_at"])

    Subscription.objects.create(
        user=payment.user,
        plan=plan,
        payment=payment,
        start_at=start_at,
        end_at=end_at,
    )
