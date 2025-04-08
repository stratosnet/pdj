import logging
import json

from django.http import HttpRequest
from django.conf import settings

from ninja import Router

from .schemas import (
    PayPalWebhookSchema,
    ErrorSchema,
)

from payments.models import (
    Processor,
)
from payments.clients import PayPalClient


logger = logging.getLogger(__name__)

router = Router()


@router.post(
    "/{webhook_secret}/paypal",
    include_in_schema=False,
    auth=None,
    response={204: None, 400: ErrorSchema},
)
def webhook_paypal(
    request: HttpRequest,
    webhook_secret: str,
    webhook_event: PayPalWebhookSchema,
):
    auth_algo = request.headers.get("PAYPAL-AUTH-ALGO")
    cert_url = request.headers.get("PAYPAL-CERT-URL")
    transmission_id = request.headers.get("PAYPAL-TRANSMISSION-ID")
    transmission_sig = request.headers.get("PAYPAL-TRANSMISSION-SIG")
    transmission_time = request.headers.get("PAYPAL-TRANSMISSION-TIME")

    print("auth_algo", auth_algo)
    print("cert_url", cert_url)
    print("transmission_id", transmission_id)
    print("transmission_sig", transmission_sig)
    print("transmission_time", transmission_time)

    try:
        processor = Processor.objects.get(webhook_secret=webhook_secret)
    except Processor.DoesNotExist:
        return 400, {"message": "Processor not set"}

    provider: PayPalClient = processor.get_provider()

    resp = provider.verify_webhook_signature(
        {
            "auth_algo": auth_algo,
            "cert_url": cert_url,
            "transmission_id": transmission_id,
            "transmission_sig": transmission_sig,
            "transmission_time": transmission_time,
        },
        processor.endpoint_secret,
        json.loads(request.body.decode("utf-8")),
    )
    print("webhook_event from request", request.body.decode("utf-8"))
    print("webhook_event from webhook_event", webhook_event.model_dump_json())
    print("resp", resp)

    status = resp.get("verification_status")
    if status != "SUCCESS":
        return 400, {"message": "Verification failed"}

    return 204, None
