import uuid
from datetime import timedelta
from urllib.parse import urljoin

from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.conf import settings
from django.contrib import admin
from django.urls import reverse
from django.utils.text import slugify
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

from core.utils import mask_secret, generate_base_secret
from core.middleware import get_current_request

from .clients.base import PaymentClient
from .clients.paypal import PayPalClient


class PlanProcessorLink(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan = models.ForeignKey(
        "Plan",
        verbose_name=_("plan"),
        related_name="links",
        on_delete=models.CASCADE,
    )
    processor = models.ForeignKey(
        "Processor",
        on_delete=models.CASCADE,
        verbose_name=_("processor"),
        related_name="links",
        help_text=_("the payment processor service"),
    )
    external_id = models.CharField(_("external_id"), max_length=128, unique=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("plan processor link")
        verbose_name_plural = _("plan processor links")
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

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(
        "accounts.Client",
        related_name="plans",
        on_delete=models.CASCADE,
        verbose_name=_("client"),
        help_text=_("The client for plan"),
    )
    name = models.CharField(
        max_length=128, verbose_name=_("name"), help_text=_("Name of the plan")
    )
    code = models.CharField(
        max_length=128,
        unique=True,
        blank=True,
        null=True,
        validators=[
            RegexValidator(
                regex=r"^[a-z0-9-]+$",
                message=_(
                    "Code must contain only lowercase letters, numbers, or hyphens"
                ),
            )
        ],
        verbose_name=_("code"),
        help_text=_(
            "Unique, machine-readable name for the plan (e.g., for syncing with external systems)"
        ),
    )
    description = models.TextField(
        null=True,
        blank=True,
        verbose_name=_("description"),
        help_text=_("Description of a plan"),
    )
    period = models.PositiveIntegerField(
        choices=PERIODS,
        verbose_name=_("period"),
        help_text=_("Billing period duration type"),
    )
    term = models.PositiveIntegerField(
        default=1,
        verbose_name=_("term"),
        help_text=_("number of periods (e.g., 1 month, 2 years)"),
    )
    price = models.DecimalField(
        max_digits=40,
        decimal_places=2,
        verbose_name=_("price"),
        help_text=_(
            "Number of periods for the subscription (e.g., if period is MONTH and term is 2, the subscription lasts 2 months)."
        ),
    )
    is_recurring = models.BooleanField(
        default=True,
        verbose_name=_("is recurring"),
        help_text=_("Whether the plan automatically renews"),
    )
    is_enabled = models.BooleanField(
        default=False,
        verbose_name=_("is enabled"),
        help_text=_("Whether the plan is available for use"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("created at"),
        help_text=_("Date and time the plan was created"),
    )
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("plan")
        verbose_name_plural = _("plans")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} (price: {self.price})"

    @property
    @admin.display(
        ordering="period",
        description=_("Billing frequency"),
    )
    def duration(self):
        period_name = self.get_period_display().lower()
        if self.term == 1:
            return _("Billed every %(period_name)s") % {"period_name": period_name}
        return _("Billed once every %(term)d %(period_name)ss") % {
            "term": self.term,
            "period_name": period_name,
        }

    def get_payment_methods(self):
        """Helper for schemas to get directly all processor as payment method"""
        for link in self.links.all():
            yield link.processor


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

    def get_active_last(
        self, user_id: int, *, plan_id: int | None, is_recurring: bool = True
    ):
        now = timezone.now()
        q = Q(
            user_id=user_id,
            plan__is_recurring=is_recurring,
            start_at__lte=now,
        )
        if plan_id:
            q &= Q(plan_id=plan_id)

        q &= Q(end_at__gte=now) | Q(end_at__isnull=True)
        return self.filter(q).order_by("-created_at").first()


class Subscription(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("user"),
        related_name="subscriptions",
        on_delete=models.CASCADE,
    )
    plan = models.ForeignKey(
        "Plan",
        verbose_name=_("plan"),
        related_name="subscriptions",
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
    start_at = models.DateTimeField(_("start at"))
    end_at = models.DateTimeField(_("end at"), null=True, blank=True)
    next_billing_at = models.DateTimeField(_("next billing at"), null=True, blank=True)
    next_billing_plan = models.ForeignKey(
        "Plan",
        verbose_name=_("future plan"),
        related_name="future_subscriptions",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    objects = SubscriptionQuerySet.as_manager()

    class Meta:
        verbose_name = _("subscription")
        verbose_name_plural = _("subscriptions")
        ordering = ["-created_at"]

    def __str__(self):
        return f"user: {self.user_id} - payment: {self.payment_id}"

    @property
    @admin.display(
        description=_("is active"),
        boolean=True,
    )
    def is_active(self):
        if not self.start_at:
            return False
        now = timezone.now()
        return self.start_at < now and (
            (self.end_at and now < self.end_at) or not self.end_at
        )

    @cached_property
    def client(self):
        return self.plan.client if self.plan else None

    def clean(self):
        if self.end_at and self.end_at <= self.start_at:
            raise ValidationError(
                _("Subscription end date should be more then start date")
            )

    def get_next_end_date(self):
        match self.plan.period:
            case self.plan.DAY:
                return self.start_at + timedelta(days=1 * self.plan.term)
            case self.plan.WEEK:
                return self.start_at + timedelta(days=7 * self.plan.term)
            case self.plan.MONTH:
                return self.start_at + timedelta(days=30 * self.plan.term)
            case self.plan.YEAR:
                return self.start_at + timedelta(days=365 * self.plan.term)


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
        settings.AUTH_USER_MODEL,
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
        verbose_name = _("payment")
        verbose_name_plural = _("payments")
        ordering = ["-created_at"]
        unique_together = ("id", "external_id")

    def __str__(self):
        return f"#{self.pk} ({self.get_status_display()})"

    @property
    def expired_at(self):
        return self.created_at + timedelta(days=3)


class Processor(models.Model):
    PAYPAL = "paypal"

    TYPES = ((PAYPAL, _("PayPal")),)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField(
        max_length=20,
        choices=TYPES,
        verbose_name=_("processor type"),
        help_text=_("The payment processor type"),
    )
    client_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name=_("client ID"),
        help_text=_("Client ID"),
    )
    secret = models.CharField(
        max_length=255,
        verbose_name=_("secret"),
        help_text=_("Secret"),
    )
    endpoint_secret = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name=_("endpoint secret"),
        help_text=_("Secret used to verify webhook payloads for provider (optional)"),
    )
    webhook_secret = models.CharField(
        max_length=40,
        unique=True,
        verbose_name=_("webhook secret"),
        help_text=_("Secret used to create link for webhook route"),
        editable=False,
        default=generate_base_secret,
    )
    is_sandbox = models.BooleanField(
        default=True,
        verbose_name=_("is sandbox"),
        help_text=_("Indicates if these credentials relates to sandbox"),
    )
    is_enabled = models.BooleanField(
        default=False,
        verbose_name=_("is active"),
        help_text=_("Indicates if these credentials are currently active"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("created at"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("updated at"))

    class Meta:
        verbose_name = _("processor")
        verbose_name_plural = _("processors")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["type", "secret"], name="unique_processor_type_secret"
            ),
        ]

    def __str__(self):
        return self.get_type_display()

    def clean(self):
        if self.type == self.PAYPAL and not self.client_id:
            raise ValidationError(_("PayPal requires a client ID"))

    @property
    @admin.display(
        ordering="webhook_secret",
        description=_("webhook URL"),
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
        description=_("client ID"),
        boolean=False,
    )
    def hidden_client_id(self):
        if not self.client_id:
            return

        return mask_secret(self.client_id)

    @property
    @admin.display(
        ordering="secret",
        description=_("secret"),
        boolean=False,
    )
    def hidden_secret(self):
        return mask_secret(self.secret)

    def get_provider(self) -> PaymentClient:
        if self.type == Processor.PAYPAL:
            return PayPalClient(
                client_id=self.client_id,
                client_secret=self.secret,
                is_sandbox=self.is_sandbox,
            )

        raise NotImplementedError("provider not set")
