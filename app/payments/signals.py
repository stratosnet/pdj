import logging
from decimal import Decimal
from datetime import datetime

from django.db import transaction
from django.utils import timezone
from django.dispatch import Signal, receiver

from customizations.models import EmailTemplate
from customizations.tasks import notify_admins
from customizations.context import get_subscription_context
from .models import (
    Plan,
    Processor,
    Subscription,
    Invoice,
)
from .exceptions import (
    SubscriptionNotFound,
    PlanNotFound,
    PaymentNotFound,
)


logger = logging.getLogger(__name__)


payment_pending = Signal()


@receiver(payment_pending)
@transaction.atomic
def on_payment_pending(
    external_sale_id: str,
    subscription_id: str,
    amount: Decimal,
    currency: str,
    created_at: datetime,
    **kwargs,
):
    try:
        sub = Subscription.objects.select_related(
            "user",
            "plan",
            "active_processor",
            "next_billing_plan",
        ).get(id=subscription_id)
    except Subscription.DoesNotExist:
        raise SubscriptionNotFound(f"Subscription '{subscription_id}' not found")

    invoice = Invoice.objects.filter(external_id=external_sale_id).first()
    if invoice:
        logger.warning(f"Invoice '{external_sale_id}' was already proceed")
        return

    Invoice.objects.create(
        subscription=sub,
        processor=sub.active_processor,
        external_id=external_sale_id,
        amount=amount,
        currency=currency,
        status=Invoice.Status.PENDING,
        created_at=created_at,
    )


payment_completed = Signal()


@receiver(payment_completed)
@transaction.atomic
def on_payment_completed(
    external_sale_id: str,
    external_invoice_id: str,
    subscription_id: str,
    amount: Decimal,
    currency: str,
    created_at: datetime,
    **kwargs,
):
    try:
        sub = Subscription.objects.select_related(
            "user",
            "plan",
            "active_processor",
            "next_billing_plan",
        ).get(id=subscription_id)
    except Subscription.DoesNotExist:
        raise SubscriptionNotFound(f"Subscription '{subscription_id}' not found")

    invoice = Invoice.objects.filter(external_id=external_sale_id).first()
    if not invoice:
        logger.warning(f"Invoice '{external_sale_id}' not found to proceed")
        return

    if invoice.status == Invoice.Status.SUCCESS:
        logger.warning(f"Invoice '{external_sale_id}' has been proceed")
        return

    invoice.status = Invoice.Status.SUCCESS
    invoice.save()

    # NOTE: Find a way to change next_billing_at time
    if sub.next_billing_plan:
        sub.plan = sub.next_billing_plan
        sub.next_billing_plan = None
        sub.save()


subscription_suspend = Signal()


@receiver(subscription_suspend)
@transaction.atomic
def on_subscription_suspend(
    subscription_id: str,
    suspended_at: datetime | None = None,
    **kwargs,
):
    try:
        sub = Subscription.objects.select_related(
            "user",
            "plan",
            "active_processor",
        ).get(id=subscription_id)
    except Subscription.DoesNotExist:
        raise SubscriptionNotFound(f"Subscription '{subscription_id}' not found")

    sub.suspend(suspended_at)

    # TODO: Check sql query
    latest_invoice = sub.invoices.order_by("-created_at").first()
    # possible because no payment sale
    if not latest_invoice:
        latest_invoice = Invoice(
            subscription=sub,
            processor=sub.active_processor,
            amount=sub.plan.price,
            status=Invoice.Status.SUCCESS,
        )

    context = get_subscription_context(latest_invoice)
    template = EmailTemplate.objects.get_by_type(EmailTemplate.SUBSCRIPTION_CANCELED)
    template.send(sub.user, context)


subscription_activate = Signal()


@receiver(subscription_activate)
@transaction.atomic
def on_subscription_activate(
    external_plan_id: str,
    external_invoice_id: str,
    subscription_id: str,
    amount: str,
    currency: str,
    start_at: datetime,
    end_at: datetime | None = None,
    **kwargs,
):
    try:
        sub = Subscription.objects.select_related(
            "user",
            "plan",
            "active_processor",
        ).get(id=subscription_id)
    except Subscription.DoesNotExist:
        raise SubscriptionNotFound(f"Subscription '{subscription_id}' not found")

    if sub.is_null:
        sub.external_id = external_invoice_id
        sub.start_at = start_at
        sub.next_billing_at = end_at
        sub.save()

        # pseudoinvoice for mailing
        invoice = Invoice(
            subscription=sub,
            processor=sub.active_processor,
            amount=amount,
            currency=currency,
            status=Invoice.Status.SUCCESS,
            updated_at=timezone.now(),
            created_at=timezone.now(),
        )

        context = get_subscription_context(invoice)
        template = EmailTemplate.objects.get_by_type(EmailTemplate.PAYMENT_SUCCESS)
        template.send(sub.user, context)
    elif sub.is_suspended:
        sub.unsuspend()
    else:
        logger.warning(f"Subscription '{subscription_id}' got activate event again")


subscription_update = Signal()


@receiver(subscription_update)
@transaction.atomic
def on_subscription_update(
    external_plan_id: str,
    subscription_id: str,
    start_at: datetime,
    end_at: datetime | None = None,
    **kwargs,
):
    try:
        sub = Subscription.objects.select_related(
            "user",
            "plan",
            "active_processor",
        ).get(id=subscription_id)
    except Subscription.DoesNotExist:
        raise SubscriptionNotFound(f"Subscription '{subscription_id}' not found")

    new_plan = (
        Plan.objects.select_related("client")
        .filter(links__external_id=external_plan_id)
        .first()
    )
    if not new_plan:
        raise PlanNotFound(f"Plan '{external_plan_id}' for switch not found")

    if sub and new_plan and sub.plan.pk != new_plan.pk:
        sub.next_billing_plan = new_plan
        sub.save(update_fields=["next_billing_plan"])


checkout_approved = Signal()


@receiver(checkout_approved)
@transaction.atomic
def on_checkout_approved(
    external_order_id: str,
    subscription_id: str,
    amount: Decimal,
    **kwargs,
):
    try:
        sub = Subscription.objects.select_related(
            "user",
            "plan",
            "active_processor",
        ).get(id=subscription_id)
    except Subscription.DoesNotExist:
        raise SubscriptionNotFound(f"Subscription '{subscription_id}' not found")

    if sub.external_id:
        logger.warning(f"Subscription '{sub.external_id}' was already approved")
        return

    if amount < sub.plan.price:
        logger.warning(
            f"Subscription '{sub.external_id}' got wrong payment amount (got: {amount}, required: {sub.plan.price})"
        )
        return

    sub.external_id = external_order_id
    sub.save(update_fields=["external_id"])

    processor: Processor = sub.active_processor
    processor.approve_order(sub.external_id)


payment_refunded = Signal()


@receiver(payment_refunded)
@transaction.atomic
def on_payment_refunded(
    subscription_id: str,
    **kwargs,
):
    try:
        sub = Subscription.objects.select_related(
            "user",
            "plan",
            "active_processor",
        ).get(id=subscription_id)
    except Subscription.DoesNotExist:
        raise SubscriptionNotFound(f"Subscription '{subscription_id}' not found")

    sub.finish(timezone.now())

    latest_invoice = sub.invoices.order_by("-created_at").first()
    if not latest_invoice:
        raise PaymentNotFound(f"Payment for subscription '{subscription_id}' not found")

    latest_invoice.status = Invoice.Status.REFUNDED
    latest_invoice.save(update_fields=["status", "updated_at"])
    logger.warning(f"Payment for subscription '{subscription_id}' has been refunded")
    # Notify admins about the refund
    notify_admins.delay(
        subject=f"Payment refunded for subscription {subscription_id}",
        message=f"Subscription ID: {subscription_id}",
    )


checkout_completed = Signal()


@receiver(checkout_completed)
@transaction.atomic
def on_checkout_completed(
    external_order_id: str,
    subscription_id: str,
    start_at: datetime,
    **kwargs,
):
    try:
        sub = Subscription.objects.select_related(
            "user",
            "plan",
            "active_processor",
        ).get(id=subscription_id)
    except Subscription.DoesNotExist:
        raise SubscriptionNotFound(f"Subscription '{subscription_id}' not found")

    if sub.invoices.first():
        logger.warning(f"Subscription '{sub.external_id}' was already proceed")
        return

    latest_sub = Subscription.objects.latest_for_user_and_client(
        client_id=sub.plan.client_id,
        user_id=sub.user.pk,
    )
    if latest_sub:
        latest_sub.finish(start_at)

    sub.start_at = start_at
    sub.end_at = sub.get_next_end_date()
    sub.save()

    Invoice.objects.create(
        subscription=sub,
        processor=sub.active_processor,
        amount=sub.plan.price,  # TODO: Get amount and currency from request
        status=Invoice.Status.SUCCESS,
    )
