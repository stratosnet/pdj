import logging
import uuid
import json

from django.http import HttpRequest
from django.conf import settings

from ninja import Router
from ninja import Cookie, Header

from core.api.authenticators import (
    authenticate_client,
    ClientAuth,
)
from .schemas import (
    CheckoutSchema,
    LinkSchema,
    UnsubscribeSchema,
    SwsubscribeSchema,
    PayPalWebhookSchema,
    ErrorSchema,
)

from payments.models import (
    Plan,
    Subscription,
    PaymentReference,
    Processor,
)
from payments.clients import PaymentClient, PayPalClient


logger = logging.getLogger(__name__)

router = Router()


@router.post(
    "/checkout",
    response={200: LinkSchema, 400: ErrorSchema},
)
@authenticate_client
def payment_checkout(
    request: HttpRequest,
    data: CheckoutSchema,
    client_token: str = Header(..., alias=ClientAuth.param_name),
):
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


@router.post(
    "/subscriptions/cancel",
    response={400: ErrorSchema},
)
@authenticate_client
def subscription_cancel(
    request: HttpRequest,
    data: UnsubscribeSchema,
    client_token: str = Header(..., alias=ClientAuth.param_name),
):
    try:
        sub = Subscription.objects.get_active_last(id=data.id)
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


@router.post(
    "/subscriptions/switch",
    response={400: ErrorSchema},
)
@authenticate_client
def subscription_switch(
    request: HttpRequest,
    data: SwsubscribeSchema,
    client_token: str = Header(..., alias=ClientAuth.param_name),
):
    # TODO
    return 204, None


@router.post(
    "/webhooks/{webhook_secret}",
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


# curl -X POST http://localhost:9060/api/payments/checkout --data '{"plan_id":1,"payment_method_id":1}' -H "X-Client-Key: 663065acff7896e9fb483fd0c4c3f05920df6112" -H "Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6IjJvRW96d2J1YkZZYjJGdFJOeVFTOGpsYXRreWhkUmluTWRwWkZGMVA0QXMifQ.eyJhY3IiOiIwIiwiYXVkIjpbIlhLT3NNZ2Q0OFRqWjAwRGJjVkRXdHQ3UzVfOXE5MVhBM3h3Ylo4Z054d2siXSwiYXV0aF90aW1lIjoxNzQzNjk0NjE2LCJhenAiOiJYS09zTWdkNDhUalowMERiY1ZEV3R0N1M1XzlxOTFYQTN4d2JaOGdOeHdrIiwiZXhwIjoxNzQzNzc0MjU1LCJpYXQiOjE3NDM3NzMyNTUsImlzcyI6Imh0dHBzOi8vc2R1Ym8ubmdyb2suaW8iLCJwZXJtaXNzaW9ucyI6W10sInNjb3BlIjoib3BlbmlkIG9mZmxpbmVfYWNjZXNzIiwic3ViIjoiYjQxZjdkODUtN2JmNC00MGY4LWE0ZWItMTdlYjRkOGYxYjYyIn0.qz54jTziOXAhWNVPgA8mThBOWrXGBy0_UmH74y0Bc_ze8MIe5AVBLBDk_TjpcIunuITvyL5y4gZ6CANjbJRnUFvR4-dwV_BeKwbZeZH8AZ7vvpzna4CV0pK37QqaqRZDOMI3IfRmN-ZnL3iZQFstTZpvLLI30q5XkWmkDTBK4QtkLiJO_aCTTmFRDuQvGHgZm_qYbX-WfysyB33p4h3CAe6JR0qgXqnrxUZwE8qp1EZKEiHP_a9KhRTnRvb6IG2GeqRiM8H9QCDzbkg34gsS3Jirbdrv9Im738wGnlYqR_cxEeBo4-ALCaYDUH1w0zscEfjy27V6ynAUxLlblQh--dvAR9C8GE6J9hV-AJT3d4TVjtEdjyH_Uw0BlQp0itZk2i0mjdx2qxtv5P0O9mvw-k5kYWsI8kVuQxZ7EHxOaYtNheIEK3Tosw7_74aT_2RvKAxd54emz1bM0__fNVhqs-Rui56hUDnZS9yygtS8M1Q2zg464mcS45Tapi3x0haN0AyXqscywn5Pu0B_KfD7nSDe3fuBCR80ip9gVJTTDgba1uvwM2_fpSrUootFgZ_k9khOkF3FOY5wSJk7d6_2uzL66EyF_zQNvm8sL_dGiZzDdLmxTpIZZvwi1ytOOJF60XL5M00Cmc89lkDkTA_yjscpDiSgNs24q3nf57xWNt8"
