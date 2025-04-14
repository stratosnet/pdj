from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext as _
from django.db import transaction
from django.db.models import Q

from requests.exceptions import RequestException
from celery import shared_task
from celery.utils.log import get_task_logger

from .models import Plan, Processor, PlanProcessorLink
from .clients.paypal import PayPalClient


logger = get_task_logger(__name__)


def find_product(paypal_client: PayPalClient, provider_product_id: str) -> bool:
    page = 1
    page_size = 10
    found = False

    while True:
        resp = paypal_client.list_products(
            page_size=page_size, page=page, total_required=True
        )
        products = resp.get("products", [])

        for product in products:
            if product["id"] == provider_product_id:
                found = True
                break

        if found or not products:
            break

        total_pages = resp.get("total_pages", 1)
        if page >= total_pages:
            break

        page += 1

    return found


def fetch_all_subscription_plans(paypal_client: PayPalClient, product_id: str):
    paypal_plans = {}
    page = 1
    page_size = 10

    while True:
        resp = paypal_client.list_subscription_plan(
            product_id=product_id,
            page_size=page_size,
            page=page,
            total_required=True,
        )

        for pplan in resp.get("plans", []):
            paypal_plans[pplan["id"]] = pplan

        total_pages = resp.get("total_pages", 1)
        if page >= total_pages:
            break

        page += 1

    return paypal_plans


@shared_task()
def paypal_sync_products():
    from accounts.models import Client

    clients = Client.objects.filter(is_enabled=True)
    for client in clients:
        processors = Processor.objects.filter(is_enabled=True, type=Processor.PAYPAL)
        for processor in processors:
            paypal_client = PayPalClient(
                processor.client_id, processor.secret, processor.is_sandbox
            )

            found = find_product(paypal_client, client.product_id)
            if not found:
                logger.info(
                    "PayPal create product for product id: %s", client.product_id
                )
                try:
                    paypal_client.create_product(client.product_id, client.product_name)
                except RequestException as e:
                    logger.error("PayPal create product failed: %s", e.response.text)
                    return

                logger.info("PayPal product created: %s", client.product_id)


@shared_task()
def paypal_sync_plans():
    plans = Plan.objects.select_related("client").filter(
        is_recurring=True, client__is_enabled=True
    )

    for plan in plans:
        client = plan.client
        processors = Processor.objects.filter(is_enabled=True, type=Processor.PAYPAL)
        for processor in processors:
            paypal_client = PayPalClient(
                processor.client_id, processor.secret, processor.is_sandbox
            )

            try:
                paypal_plans = fetch_all_subscription_plans(
                    paypal_client, client.product_id
                )
            except RequestException as e:
                logger.error("PayPal fetch plan list failed: %s", e.response.text)
                continue

            # NOTE: Check multiple references
            try:
                pr = plan.links.get(
                    processor=processor,
                )
            except PlanProcessorLink.DoesNotExist:
                pr = None

            if pr is None and plan.is_enabled:
                description = (
                    plan.description
                    if plan.description
                    else f"Description for the plan: {plan.name}"
                )
                if len(description) > 127:
                    description = description[:124] + "..."

                try:
                    resp = paypal_client.create_subscription_plan(
                        client.product_id,
                        plan.name,
                        description,
                        plan.get_period_display().capitalize(),
                        plan.term,
                        f"{plan.price:.2f}",
                        settings.DEFAULT_CURRENCY,
                    )
                except RequestException as e:
                    logger.error("PayPal create plan failed: %s", e.response.text)
                    continue

                logger.info("PayPal plan created: %s", resp["id"])

                plan.links.create(external_id=resp["id"], processor=processor)
            elif pr is not None:
                try:
                    paypal_plan = paypal_plans[pr.external_id]
                except KeyError:
                    logger.info(f"Plan '{pr.external_id}' not found on PayPal")
                    continue

                if plan.is_enabled and paypal_plan["status"] != "ACTIVE":
                    try:
                        paypal_client.activate_subscription_plan(pr.external_id)
                    except RequestException as e:
                        logger.info(
                            "PayPal plan activation failed: %s", e.response.text
                        )
                        continue

                    logger.info("PayPal plan activated: %s", pr.external_id)
                elif not plan.is_enabled and paypal_plan["status"] == "ACTIVE":
                    try:
                        paypal_client.deactivate_subscription_plan(pr.external_id)
                    except RequestException as e:
                        logger.info(
                            "PayPal plan deactivation failed: %s", e.response.text
                        )
                        continue

                    logger.info("PayPal plan deactivation: %s", pr.external_id)
                else:
                    logger.info(
                        "PayPal plan '%s' does not require any update",
                        pr.external_id,
                    )
