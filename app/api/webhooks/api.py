import logging
import json
from decimal import Decimal

from django.http import HttpRequest
from django.utils.dateparse import parse_datetime

from ninja import Router

from payments.models import (
    Processor,
)
from payments.clients import PayPalClient
from payments.exceptions import (
    PaymentException,
)
from payments.signals import (
    payment_completed,
    subscription_suspend,
    subscription_activate,
    subscription_update,
)
from .schemas import (
    ErrorSchema,
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
            # sent on next recurring payment
            case "PAYMENT.SALE.COMPLETED":
                external_id = webhook_event["resource"]["billing_agreement_id"]
                amount = Decimal(webhook_event["resource"]["amount"]["total"])
                currency = webhook_event["resource"]["amount"]["currency"]
                start_at = parse_datetime(webhook_event["resource"]["create_time"])
                payment_completed.send(
                    sender=None,
                    external_id=external_id,
                    amount=amount,
                    currency=currency,
                    start_at=start_at,
                )
            # send as first event when subscription created and when unsuspended
            case "BILLING.SUBSCRIPTION.ACTIVATED":
                id = webhook_event["resource"]["id"]
                custom_id = webhook_event["resource"]["custom_id"]
                plan_id = webhook_event["resource"]["plan_id"]
                last_payment = webhook_event["resource"]["billing_info"]["last_payment"]
                amount = Decimal(last_payment["amount"]["value"])
                currency = last_payment["amount"]["currency_code"]
                start_at = parse_datetime(webhook_event["resource"]["start_time"])
                end_at = parse_datetime(
                    webhook_event["resource"]["billing_info"]["next_billing_time"]
                )
                subscription_activate.send(
                    sender=None,
                    id=id,
                    plan_id=plan_id,
                    custom_id=custom_id,
                    amount=amount,
                    currency=currency,
                    start_at=start_at,
                    end_at=end_at,
                )
            # when plan changed
            case "BILLING.SUBSCRIPTION.UPDATED":
                custom_id = webhook_event["resource"]["custom_id"]
                plan_id = webhook_event["resource"]["plan_id"]
                start_at = parse_datetime(webhook_event["resource"]["start_time"])
                end_at = parse_datetime(
                    webhook_event["resource"]["billing_info"]["next_billing_time"]
                )
                subscription_update.send(
                    sender=None,
                    plan_id=plan_id,
                    custom_id=custom_id,
                    start_at=start_at,
                    end_at=end_at,
                )
            # when suspended
            case "BILLING.SUBSCRIPTION.SUSPENDED":
                custom_id = webhook_event["resource"]["custom_id"]
                suspended_at = parse_datetime(
                    webhook_event["resource"]["status_update_time"]
                )
                subscription_suspend.send(
                    sender=None,
                    custom_id=custom_id,
                    suspended_at=suspended_at,
                )
            case _:
                logger.warning(
                    f"Not supported event type: {webhook_event['event_type']}"
                )
                return 200, {"message": "Event match not supported"}
    except PaymentException as e:
        logger.warning(f"Payment error: {e.args}")
        return 400, {"message": f"Webhook error: {e.args[0]}"}
    except Exception as e:
        logger.exception(e)
        return 500, {"message": "Unhandled error"}

    return 204, None
