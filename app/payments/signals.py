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
    Invoice,
    Payment,
)
from .exceptions import (
    PaymentNotFound,
    PaymentWrongStatus,
    SubscriptionNotFound,
    PlanNotFound,
)


logger = logging.getLogger(__name__)


payment_completed = Signal()
subscription_suspend = Signal()
subscription_activate = Signal()
subscription_update = Signal()


@receiver(payment_completed)
@transaction.atomic
def on_payment_completed(
    external_id: str,
    amount: Decimal,
    currency: str,
    start_at: datetime,
    **kwargs,
):
    try:
        invoice = Invoice.objects.select_related(
            "user",
            "processor",
        ).get(external_id=external_id)
    except Invoice.DoesNotExist:
        raise PaymentNotFound(f"Last payment for external id '{external_id}' not found")

    last_payment = (
        invoice.payments.select_related("subscription").order_by("-created_at").first()
    )
    if not last_payment:
        raise PaymentNotFound(f"Last payment for external id '{external_id}' not found")

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


@receiver(subscription_suspend)
@transaction.atomic
def on_subscription_suspend(
    custom_id: str,
    suspended_at: datetime | None = None,
    **kwargs,
):
    try:
        invoice = Invoice.objects.select_related(
            "user",
            "processor",
        ).get(id=custom_id)
    except Invoice.DoesNotExist:
        raise PaymentNotFound(f"Last payment for custom id '{custom_id}' not found")

    payment = (
        invoice.payments.select_related("subscription").order_by("-created_at").first()
    )
    sub = payment.subscription
    sub.suspend(suspended_at)

    context = get_subscription_context(sub)
    template = EmailTemplate.objects.get_by_type(EmailTemplate.SUBSCRIPTION_CANCELED)
    template.send(invoice.user, context)


@receiver(subscription_activate)
@transaction.atomic
def on_subscription_activate(
    plan_id: str,
    id: str,
    custom_id: str,
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
        ).get(id=custom_id)
    except Invoice.DoesNotExist:
        raise PaymentNotFound(f"Last payment for custom id '{custom_id}' not found")

    payment = (
        invoice.payments.select_related("subscription").order_by("-created_at").first()
    )
    if not payment:
        raise PaymentNotFound(f"Last payment for custom id '{custom_id}' not found")

    # first event when user has bought subscription
    if payment.status == Payment.PENDING:
        payment.status = Payment.SUCCESS
        payment.amount = amount
        payment.currency = currency
        payment.save(update_fields=["status", "amount", "currency"])

        invoice.external_id = id
        invoice.save(update_fields=["external_id"])

        plan = (
            Plan.objects.select_related("client")
            .filter(links__external_id=plan_id)
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
            f"Payment for custom id '{custom_id}' has wrong status (got: {payment.status}, should be: {Payment.PENDING})"
        )


@receiver(subscription_update)
@transaction.atomic
def on_subscription_update(
    plan_id: str,
    custom_id: str,
    start_at: datetime,
    end_at: datetime | None = None,
    **kwargs,
):
    try:
        invoice = Invoice.objects.select_related(
            "user",
            "processor",
        ).get(id=custom_id)
    except Invoice.DoesNotExist:
        raise PaymentNotFound(f"Last payment for custom id '{custom_id}' not found")

    payment = (
        invoice.payments.select_related("subscription", "subscription__plan")
        .order_by("-created_at")
        .first()
    )
    sub = payment.subscription if payment else None
    if sub and sub.plan.pk != plan_id:
        new_plan = Plan.objects.filter(links__external_id=plan_id).first()
        if not new_plan:
            raise PlanNotFound(f"Plan '{plan_id}' for switch not found")

        sub.next_billing_plan = new_plan
        sub.save(update_fields=["next_billing_plan"])
