import logging
from decimal import Decimal
from datetime import datetime

from django.db import transaction
from django.dispatch import Signal, receiver

from customizations.models import EmailTemplate
from customizations.context import get_subscription_context
from .models import (
    Subscription,
    Plan,
    Processor,
    Invoice,
    Payment,
)
from .exceptions import (
    InvoiceNotFound,
    PaymentNotFound,
    PaymentWrongStatus,
    SubscriptionNotFound,
    PlanNotFound,
)


logger = logging.getLogger(__name__)


payment_completed = Signal()


@receiver(payment_completed)
@transaction.atomic
def on_payment_completed(
    invoice_id: str,
    amount: Decimal,
    currency: str,
    start_at: datetime,
    **kwargs,
):
    try:
        invoice = Invoice.objects.select_related(
            "user",
            "processor",
        ).get(id=invoice_id)
    except Invoice.DoesNotExist:
        raise InvoiceNotFound(f"Invoice '{invoice_id}' not found")

    last_payment = (
        invoice.payments.select_related("subscription").order_by("-created_at").first()
    )
    if not last_payment:
        raise PaymentNotFound(f"Last payment for invoice '{invoice_id}' not found")

    sub = last_payment.subscription
    if not sub:
        raise SubscriptionNotFound(
            f"Subscription not found for payment '{last_payment.id}'"
        )

    # if plan was changed for future recurring, we should apply it here
    next_billing_plan = sub.next_billing_plan if sub.next_billing_plan_id else sub.plan

    sub.finish(start_at)

    # new payment record + new sub record to combine subscription recurring chunks
    new_payment = Payment.objects.create(
        invoice=invoice,
        amount=amount,
        currency=currency,
        status=Payment.SUCCESS,
    )
    sub = Subscription(
        user=invoice.user,
        plan=next_billing_plan,
        payment=new_payment,
        start_at=start_at,
    )
    sub.next_billing_at = sub.get_next_end_date()
    sub.save()


subscription_suspend = Signal()


@receiver(subscription_suspend)
@transaction.atomic
def on_subscription_suspend(
    invoice_id: str,
    suspended_at: datetime | None = None,
    **kwargs,
):
    try:
        invoice = Invoice.objects.select_related(
            "user",
            "processor",
        ).get(id=invoice_id)
    except Invoice.DoesNotExist:
        raise InvoiceNotFound(f"Invoice '{invoice_id}' not found")

    payment = (
        invoice.payments.select_related("subscription").order_by("-created_at").first()
    )
    sub = payment.subscription
    sub.suspend(suspended_at)

    context = get_subscription_context(sub)
    template = EmailTemplate.objects.get_by_type(EmailTemplate.SUBSCRIPTION_CANCELED)
    template.send(invoice.user, context)


subscription_activate = Signal()


@receiver(subscription_activate)
@transaction.atomic
def on_subscription_activate(
    external_plan_id: str,
    external_invoice_id: str,
    invoice_id: str,
    amount: str,
    currency: str,
    start_at: datetime,
    end_at: datetime | None = None,
    **kwargs,
):
    try:
        invoice = Invoice.objects.select_related(
            "user",
            "processor",
        ).get(id=invoice_id)
    except Invoice.DoesNotExist:
        raise InvoiceNotFound(f"Invoice '{invoice_id}' not found")

    payment = (
        invoice.payments.select_related("subscription").order_by("-created_at").first()
    )
    if not payment:
        raise PaymentNotFound(f"Last payment for invoice '{invoice_id}' not found")

    # first event when user has bought subscription
    if payment.status == Payment.PENDING:
        payment.status = Payment.SUCCESS
        payment.amount = amount
        payment.currency = currency
        payment.save(update_fields=["status", "amount", "currency"])

        invoice.external_id = external_invoice_id
        invoice.save(update_fields=["external_id"])

        plan = (
            Plan.objects.select_related("client")
            .filter(links__external_id=external_plan_id)
            .first()
        )
        sub = Subscription.objects.latest_for_user_and_client(
            user_id=invoice.user.pk,
            client_id=plan.client_id,
        )

        # so if we had previous one, we should reset all fields related to statuses
        # mostly this is related for non recurring logic
        if sub:
            sub.finish(start_at)

        sub = Subscription.objects.create(
            user=invoice.user,
            plan=plan,
            payment=payment,
            start_at=start_at,
            next_billing_at=end_at,
        )

        context = get_subscription_context(sub)
        template = EmailTemplate.objects.get_by_type(EmailTemplate.PAYMENT_SUCCESS)
        template.send(invoice.user, context)
        return

    # for reactivation only, same event
    elif payment.subscription and payment.subscription.is_suspended:
        payment.subscription.unsuspend()
    else:
        raise PaymentWrongStatus(
            f"Payment for id '{invoice_id}' has wrong status (got: {payment.status}, should be: {Payment.PENDING})"
        )


subscription_update = Signal()


@receiver(subscription_update)
@transaction.atomic
def on_subscription_update(
    external_plan_id: str,
    invoice_id: str,
    start_at: datetime,
    end_at: datetime | None = None,
    **kwargs,
):
    try:
        invoice = Invoice.objects.select_related(
            "user",
            "processor",
        ).get(id=invoice_id)
    except Invoice.DoesNotExist:
        raise InvoiceNotFound(f"Invoice '{invoice_id}' not found")

    payment = (
        invoice.payments.select_related("subscription", "subscription__plan")
        .order_by("-created_at")
        .first()
    )
    sub = payment.subscription if payment else None

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
    invoice_id: str,
    **kwargs,
):
    try:
        invoice = Invoice.objects.select_related(
            "user",
            "processor",
        ).get(id=invoice_id)
    except Invoice.DoesNotExist:
        raise InvoiceNotFound(f"Invoice '{invoice_id}' not found")

    if not invoice.external_id:
        invoice.external_id = external_order_id
        invoice.save(update_fields=["external_id"])

    processor: Processor = invoice.processor
    processor.approve_order(external_order_id)


checkout_completed = Signal()


@receiver(checkout_completed)
@transaction.atomic
def on_checkout_completed(
    invoice_id: str,
    plan_id: str,
    start_at: datetime,
    **kwargs,
):
    try:
        invoice = Invoice.objects.select_related(
            "user",
            "processor",
        ).get(id=invoice_id)
    except Invoice.DoesNotExist:
        raise InvoiceNotFound(f"Invoice '{invoice_id}' not found")

    last_payment = (
        invoice.payments.select_related("subscription").order_by("-created_at").first()
    )
    if not last_payment:
        raise PaymentNotFound(f"Last payment for invoice '{invoice_id}' not found")

    if last_payment.status == Payment.SUCCESS:
        logger.warning(
            f"Checkout already has been proceed for {invoice_id}, but got same event again"
        )
        return

    try:
        sub = last_payment.subscription
        sub.finish(start_at)
    except Subscription.DoesNotExist:
        pass

    last_payment.status = Payment.SUCCESS
    last_payment.save(update_fields=["status"])

    sub = Subscription(
        user=invoice.user,
        plan_id=plan_id,
        payment=last_payment,
        start_at=start_at,
    )
    sub.end_at = sub.get_next_end_date()
    sub.save()
