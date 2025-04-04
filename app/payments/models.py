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
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError

from core.utils import mask_secret, generate_enpoint_secret
from core.middleware import get_current_request

from .clients.base import PaymentClient
from .clients.paypal import PayPalClient


class Plan(models.Model):
    DAY = 1
    WEEK = 2
    MONTH = 3
    YEAR = 4

    PERIODS = (
        (DAY, _("Day")),
        (WEEK, _("Week")),
        (MONTH, _("Month")),
        (YEAR, _("Year")),
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

    links = GenericRelation("PaymentReference")

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


class SubscriptionManager(models.Manager):
    def get_active_last(self, id: int, is_recurring: bool = True):
        now = timezone.now()
        return (
            self.select_related("plan")
            .filter(
                Q(
                    pk=id,
                    plan__is_reccuring=is_recurring,
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
    tier = models.ForeignKey(
        "Plan",
        verbose_name=_("plan"),
        related_name="subscriptions",
        on_delete=models.CASCADE,
    )
    order = models.ForeignKey(
        "Order",
        verbose_name=_("order"),
        related_name="subscriptions",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    start_at = models.DateTimeField(_("start at"), editable=False)
    end_at = models.DateTimeField(_("end at"), null=True, blank=True, editable=False)
    next_billing_at = models.DateTimeField(
        _("next billing at"), null=True, blank=True, editable=False
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    links = GenericRelation("PaymentReference")

    objects = SubscriptionManager()

    class Meta:
        verbose_name = _("Subscription")
        verbose_name_plural = _("Subscriptions")
        ordering = ["-created_at"]

    def __str__(self):
        return f"user: {self.user.user_id} - tier: {self.tier.tier_id}"

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


class Order(models.Model):

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
    user = models.ForeignKey(
        "accounts.SSOUser",
        verbose_name=_("user"),
        related_name="orders",
        on_delete=models.CASCADE,
    )
    amount = models.DecimalField(_("amount"), max_digits=16, decimal_places=2)
    currency = models.CharField(
        _("currency"), max_length=3, default=settings.DEFAULT_CURRENCY
    )
    status = models.PositiveIntegerField(_("status"), choices=STATUSES, default=PENDING)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    extra_data = JSONField(_("extra data"), null=True)

    class Meta:
        verbose_name = _("Order")
        verbose_name_plural = _("Orders")
        ordering = ["-created_at"]

    def __str__(self):
        return f"#{self.pk} ({self.get_status_display()})"

    def expired_at(self):
        return self.created_at + timedelta(days=3)

    @property
    def payment_id(self):
        return self.pk.hex


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
        if settings.PAYMENT_DOMAIN:
            return urljoin(settings.PAYMENT_DOMAIN, path)

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


class PaymentReference(models.Model):
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        verbose_name=_("Content Type"),
        help_text=_("The type of object this payment relates to"),
    )
    object_id = models.PositiveIntegerField(
        verbose_name=_("Object ID"), help_text=_("The ID of the related object")
    )
    content_object = GenericForeignKey("content_type", "object_id")

    processor = models.ForeignKey(
        "Processor",
        on_delete=models.CASCADE,
        verbose_name=_("Processor"),
        help_text=_("The payment processor service"),
    )
    external_id = models.CharField(
        max_length=128,
        verbose_name=_("External ID"),
        help_text=_("Unique identifier from the payment provider"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))

    class Meta:
        verbose_name = _("Payment Reference")
        verbose_name_plural = _("Payment References")
        unique_together = ("processor", "external_id")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
        ]

    def __str__(self):
        return f"{self.processor}:{self.object_id} (ID: {self.external_id})"
