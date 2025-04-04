from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext as _
from django.db import transaction
from django.db.models import Q

from requests.exceptions import RequestException
from celery import shared_task
from celery.utils.log import get_task_logger

from .models import Plan, Processor, PaymentReference
from .clients.paypal import PayPalClient


logger = get_task_logger(__name__)


@shared_task()
def paypal_sync_plans():
    from accounts.models import Client

    clients = Client.objects.filter(is_enabled=True)
    for client in clients:
        plans = client.plans.filter(is_recurring=True)

        for plan in plans:
            processors = Processor.objects.filter(
                is_enabled=True, processor_type=Processor.PAYPAL
            )
            for processor in processors:
                paypal_client = PayPalClient(
                    processor.client_id, processor.secret, processor.is_sandbox
                )

                provider_product_id = f"{client.sku_prefix}-{client.pk}"
                provider_product_name = client.product_name

                resp = paypal_client.list_products()
                products = resp.get("products", [])

                found = False
                for product in products:
                    if product["id"] == provider_product_id:
                        found = True
                        break

                if not found:
                    logger.info(
                        "PayPal create product for product id: %s", provider_product_id
                    )
                    try:
                        paypal_client.create_product(
                            provider_product_id, provider_product_name
                        )
                    except RequestException as e:
                        logger.error(
                            "PayPal create product failed: %s", e.response.text
                        )
                        return

                    logger.info("PayPal product created: %s", provider_product_id)

                # TODO: Add pagination
                try:
                    resp = paypal_client.list_subscription_plan(provider_product_id, 20)
                    paypal_plans = {}
                    for pplan in resp.get("plans", []):
                        paypal_plans[pplan["id"]] = pplan
                except RequestException as e:
                    logger.error("PayPal fetch plan list failed: %s", e.response.text)
                    continue

                # NOTE: Check multiple references
                try:
                    pr = plan.links.get(
                        processor=processor,
                    )
                except PaymentReference.DoesNotExist:
                    pr = None

                if pr is None and plan.is_enabled:
                    description = (
                        plan.description
                        if plan.description
                        else f"Description for the plan: {plan.name}"
                    )

                    try:
                        resp = paypal_client.create_subscription_plan(
                            provider_product_id,
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
