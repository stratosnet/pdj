import uuid
from datetime import timedelta
from urllib.parse import urljoin

from django.db import models
from django.db.models import JSONField, Q
from django.utils import timezone
from django.conf import settings
from django.contrib import admin
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

from core.utils import mask_secret, generate_enpoint_secret
from core.middleware import get_current_request

from .clients.base import PaymentClient
from .clients.paypal import PayPalClient


class PlanProcessorLink(models.Model):

    plan = models.ForeignKey(
        "Plan",
        verbose_name=_("plan"),
        related_name="links",
        on_delete=models.CASCADE,
    )
    processor = models.ForeignKey(
        "Processor",
        on_delete=models.CASCADE,
        verbose_name=_("Processor"),
        related_name="links",
        help_text=_("The payment processor service"),
    )
    external_id = models.CharField(_("external_id"), max_length=128, unique=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("Plan processor link")
        verbose_name_plural = _("Plan processor links")
        ordering = ["-created_at"]


class Plan(models.Model):
    DAY = 1
    WEEK = 2
    MONTH = 3
    YEAR = 4

    PERIODS = (
        (DAY, "DAY"),
        (WEEK, "WEEK"),
        (MONTH, "MONTH"),
        (YEAR, "YEAR"),
    )

    client = models.ForeignKey(
        "accounts.Client",
        related_name="plans",
        on_delete=models.CASCADE,
        verbose_name=_("Client"),
        help_text=_("The client for plan"),
    )
    name = models.CharField(
        max_length=128, verbose_name=_("Name"), help_text=_("Name of the plan")
    )
    description = models.TextField(
        null=True,
        blank=True,
        verbose_name=_("Description"),
        help_text=_("Description of a plan"),
    )
    period = models.PositiveIntegerField(
        choices=PERIODS,
        verbose_name=_("Period"),
        help_text=_("Billing period duration type"),
    )
    term = models.IntegerField(
        default=1,
        verbose_name=_("Term"),
        help_text=_("Number of periods (e.g., 1 month, 2 years)"),
    )
    price = models.DecimalField(
        max_digits=40,
        decimal_places=2,
        verbose_name=_("Price"),
        help_text=_("Price of the plan in the specified currency"),
    )
    is_recurring = models.BooleanField(
        default=True,
        verbose_name=_("Is Recurring"),
        help_text=_("Whether the plan automatically renews"),
    )
    is_enabled = models.BooleanField(
        default=False,
        verbose_name=_("Is Enabled"),
        help_text=_("Whether the plan is available for use"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Created At"),
        help_text=_("Date and time the plan was created"),
    )
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("Plan")
        verbose_name_plural = _("Plans")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} (Price: {self.price})"

    @property
    @admin.display(
        ordering="period",
        description=_("Duration"),
    )
    def duration(self):
        term_suffix = "s" if self.term > 1 else ""
        return _("%(period)sly for %(term)d %(period)s%(term_suffix)s") % {
            "term_suffix": term_suffix,
            "period": self.get_period_display(),
            "term": self.term,
        }


class SubscriptionQuerySet(models.QuerySet):
    def get_user_subscriptions(self, user_id: int):
        now = timezone.now()
        return self.filter(
            Q(
                user_id=user_id,
                start_at__lte=now,
            ),
            Q(end_at__gte=now) | Q(end_at__isnull=True),
        ).order_by("-created_at")

    def get_active_last(self, plan_id: int, user_id: int, is_recurring: bool = True):
        now = timezone.now()
        return (
            self.filter(
                Q(
                    user_id=user_id,
                    plan_id=plan_id,
                    plan__is_recurring=is_recurring,
                    start_at__lte=now,
                ),
                Q(end_at__gte=now) | Q(end_at__isnull=True),
            )
            .order_by("-created_at")
            .first()
        )


class Subscription(models.Model):
    user = models.ForeignKey(
        "accounts.SSOUser",
        verbose_name=_("user"),
        related_name="subscriptions",
        on_delete=models.CASCADE,
    )
    plan = models.ForeignKey(
        "Plan",
        verbose_name=_("plan"),
        related_name="payments",
        on_delete=models.CASCADE,
    )
    payment = models.OneToOneField(
        "Payment",
        verbose_name=_("payment"),
        related_name="subscription",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    start_at = models.DateTimeField(_("start at"), editable=False)
    end_at = models.DateTimeField(_("end at"), null=True, blank=True, editable=False)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    objects = SubscriptionQuerySet.as_manager()

    class Meta:
        verbose_name = _("Subscription")
        verbose_name_plural = _("Subscriptions")
        ordering = ["-created_at"]

    def __str__(self):
        return f"user: {self.user_id} - payment: {self.payment_id}"

    @property
    def is_active(self):
        now = timezone.now()
        return self.start_at < now and (now < self.end_at or not self.end_at)

    def update_end_date(self):
        if self.plan.period == self.plan.DAY:
            self.end_at = self.start_at + timedelta(days=1 * self.plan.term)
        elif self.plan.period == self.plan.WEEK:
            self.end_at = self.start_at + timedelta(days=7 * self.plan.term)
        elif self.plan.period == self.plan.MONTH:
            self.end_at = self.start_at + timedelta(days=30 * self.plan.term)
        elif self.plan.period == self.plan.YEAR:
            self.end_at = self.start_at + timedelta(days=365 * self.plan.term)
        else:
            self.end_at = self.start_at


class Payment(models.Model):

    PENDING = 1
    HOLD = 2
    CANCELED = 3
    FAILURE = 4
    SUCCESS = 5
    EXPIRED = 6

    STATUSES = (
        (PENDING, _("Pending")),
        (HOLD, _("Hold")),
        (CANCELED, _("Canceled")),
        (FAILURE, _("Failure")),
        (SUCCESS, _("Success")),
        (EXPIRED, _("Expired")),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    external_id = models.CharField(_("external_id"), max_length=128)
    user = models.ForeignKey(
        "accounts.SSOUser",
        verbose_name=_("user"),
        related_name="payments",
        on_delete=models.CASCADE,
    )
    processor = models.ForeignKey(
        "Processor",
        verbose_name=_("processor"),
        related_name="payments",
        on_delete=models.CASCADE,
    )
    amount = models.DecimalField(_("amount"), max_digits=16, decimal_places=2)
    currency = models.CharField(
        _("currency"), max_length=3, default=settings.DEFAULT_CURRENCY
    )
    status = models.PositiveIntegerField(_("status"), choices=STATUSES, default=PENDING)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("Payment")
        verbose_name_plural = _("Payments")
        ordering = ["-created_at"]
        unique_together = ("id", "external_id")

    def __str__(self):
        return f"#{self.pk} ({self.get_status_display()})"

    @property
    def expired_at(self):
        return self.created_at + timedelta(days=3)


class Processor(models.Model):
    PAYPAL = "paypal"

    PROCESSOR_CHOICES = ((PAYPAL, _("PayPal")),)

    processor_type = models.CharField(
        max_length=20,
        choices=PROCESSOR_CHOICES,
        verbose_name=_("Processor Type"),
        help_text=_("The payment processor type"),
    )

    client_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name=_("Client ID"),
        help_text=_("Client ID"),
    )
    secret = models.CharField(
        max_length=255,
        verbose_name=_("Secret"),
        help_text=_("Secret"),
    )

    endpoint_secret = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name=_("Endpoint Secret"),
        help_text=_("Secret used to verify webhook payloads for provider (optional)"),
    )
    webhook_secret = models.CharField(
        max_length=40,
        unique=True,
        verbose_name=_("Webhook Secret"),
        help_text=_("Secret used to create link for webhook route"),
        editable=False,
        default=generate_enpoint_secret,
    )

    is_sandbox = models.BooleanField(
        default=True,
        verbose_name=_("Is Sandbox"),
        help_text=_("Indicates if these credentials relates to sandbox"),
    )
    is_enabled = models.BooleanField(
        default=False,
        verbose_name=_("Is Active"),
        help_text=_("Indicates if these credentials are currently active"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated At"))

    class Meta:
        verbose_name = _("Processor")
        verbose_name_plural = _("Processors")
        ordering = ["processor_type"]
        unique_together = ("processor_type", "secret")

    def __str__(self):
        return self.get_processor_type_display()

    def clean(self):
        if self.processor_type == self.PAYPAL and not self.client_id:
            raise ValidationError(_("PayPal requires a Client ID"))

    @property
    @admin.display(
        ordering="webhook_secret",
        description=_("Webhook URL"),
        boolean=False,
    )
    def webhook_url(self):
        path = reverse("api-1.0.0:webhook_paypal", args=(self.webhook_secret,))
        if settings.PDJ_PAY_DOMAIN:
            return urljoin(settings.PDJ_PAY_DOMAIN, path)

        request = get_current_request()
        return request.build_absolute_uri(path)

    @property
    @admin.display(
        ordering="client_id",
        description=_("Client ID"),
        boolean=False,
    )
    def hidden_client_id(self):
        if not self.client_id:
            return

        return mask_secret(self.client_id)

    @property
    @admin.display(
        ordering="secret",
        description=_("Secret"),
        boolean=False,
    )
    def hidden_secret(self):
        return mask_secret(self.secret)

    def get_provider(self) -> PaymentClient:
        if self.processor_type == Processor.PAYPAL:
            return PayPalClient(
                client_id=self.client_id,
                client_secret=self.secret,
                is_sandbox=self.is_sandbox,
            )

        raise NotImplementedError("provider not set")
