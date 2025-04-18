from django.utils.translation import gettext_lazy as _
from django.http.request import HttpRequest
from django.conf import settings
from django.utils import timezone
from dateutil.relativedelta import relativedelta

from core.utils import get_default_context
from accounts.models import Client
from payments.models import Plan, Subscription, Invoice, Processor
from .models import Theme


def get_test_context(request: HttpRequest):
    """Context for testing email templates"""
    client = Client(name="Test client", home_url="https://localhost")
    plan = Plan(
        client=client,
        name="Test plan",
        period=Plan.MONTH,
        term=1,
        price=10,
        is_recurring=True,
    )
    processor = Processor(
        type=Processor.PAYPAL,
    )
    sub = Subscription(
        user=request.user,
        plan=plan,
        created_at=timezone.now(),
        end_at=None,
        next_billing_at=timezone.now() + relativedelta(months=1),
    )
    invoice = Invoice(
        subscription=sub,
        user=request.user,
        processor=processor,
        amount=plan.price,
        currency=settings.DEFAULT_CURRENCY,
        created_at=timezone.now(),
        updated_at=timezone.now(),
    )

    return get_subscription_context(invoice)


def get_subscription_context(invoice: Invoice):
    context = get_default_context()

    sub = invoice.subscription
    context["subscription"] = sub.context
    if sub.plan_id:
        context["plan"] = sub.plan.context
        if sub.plan.client_id:
            context["client"] = sub.plan.client.context

    if sub.user_id:
        context["user"] = sub.user.context

    context["invoice"] = invoice.context
    if sub.active_processor_id:
        context["processor"] = sub.active_processor.context

    theme = Theme.objects.filter(active=True).first()
    if theme:
        context["theme"] = theme.context
    return context
