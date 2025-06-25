from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext as _
from django.db import transaction
from django.db.models import Q

from requests.exceptions import RequestException
from celery import shared_task
from celery.utils.log import get_task_logger

from ..models import Plan, Processor, PlanProcessorLink
from ..clients.paypal import PayPalClient


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
def sync_products():
    from accounts.models import Client

    clients = Client.objects.filter(is_enabled=True)
    for client in clients:
        processors = Processor.objects.filter(
            is_enabled=True, type=Processor.Type.PAYPAL
        )
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
def sync_plan(plan_id: str):
    try:
        plan = Plan.objects.select_related("client").get(
            pk=plan_id,
            client__is_enabled=True,
            is_default=False,
            is_recurring=True,
        )
    except Plan.DoesNotExist:
        logger.warning(f"Plan '{plan_id}' not found")
        return

    for pr in PlanProcessorLink.objects.select_related("processor").filter(
        Q(processor__type=Processor.Type.PAYPAL, processor__is_enabled=True)
        & Q(plan=plan)
    ):
        processor = pr.processor
        paypal_client = PayPalClient(
            processor.client_id, processor.secret, processor.is_sandbox
        )

        try:
            paypal_plans = fetch_all_subscription_plans(
                paypal_client, plan.client.product_id
            )
        except RequestException as e:
            logger.error("PayPal fetch plan list failed: %s", e.response.text)
            continue

        try:
            pr = plan.links.get(
                processor=processor,
            )
        except PlanProcessorLink.DoesNotExist:
            pr = None

        description = (
            plan.description
            if plan.description
            else f"Description for the plan: {plan.name}"
        )
        if len(description) > 127:
            description = description[:124] + "..."

        interval_unit = plan.get_period_display().capitalize()
        interval_count = plan.term
        price = f"{plan.price:.2f}"
        currency = settings.DEFAULT_CURRENCY

        if pr.external_id is None:
            try:
                resp = paypal_client.create_subscription_plan(
                    plan.client.product_id,
                    plan.name,
                    description,
                    interval_unit,
                    interval_count,
                    price,
                    currency,
                )
            except RequestException as e:
                logger.error("PayPal create plan failed: %s", e.response.text)
                continue

            logger.info("PayPal plan created: %s", resp["id"])

            pr.external_id = resp["id"]
            pr.synced_at = timezone.now()
            pr.save(update_fields=["external_id", "synced_at"])
        else:
            try:
                paypal_plan = paypal_plans[pr.external_id]
            except KeyError:
                logger.info(f"Plan '{pr.external_id}' not found on PayPal")
                continue

            if paypal_plan["status"] != "ACTIVE":
                logger.info("PayPal plan not activate to update: %s", pr.external_id)
                continue

            # NOTE: Possible optimization of check diff between save states in order to avoid
            # addition paypal api call, but not required right now
            try:
                paypal_client.update_subscription_plan(
                    pr.external_id,
                    plan.name,
                    description,
                )
            except RequestException as e:
                if e.response.status_code != 422:
                    raise e
                logger.warning(
                    f"PayPal failed to proceed update subscription plan, details: {e.response.text}"
                )

            try:
                paypal_client.update_pricing_plan(
                    pr.external_id,
                    price,
                    currency,
                )
            except RequestException as e:
                if e.response.status_code != 422:
                    raise e
                logger.warning(
                    f"PayPal failed to proceed update pricing plan, details: {e.response.text}"
                )
            pr.synced_at = timezone.now()
            pr.save(update_fields=["synced_at"])
