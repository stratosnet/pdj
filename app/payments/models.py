import uuid
from datetime import timedelta, datetime
from decimal import Decimal

from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q, OuterRef, Subquery
from django.utils import timezone
from django.conf import settings
from django.contrib import admin
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils.safestring import mark_safe
from django.utils.html import format_html

from core.utils import mask_secret, generate_base_secret, build_full_path

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
    external_id = models.CharField(
        _("external_id"), max_length=128, unique=True, null=True, blank=True
    )
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

    @cached_property
    def context(self):
        return {
            "name": self.name,
            "client": self.client.context,
            "period": self.get_period_display().lower().capitalize(),
            "term": self.term,
            "price": f"{self.price:.2f}",
            "is_recurring": self.is_recurring,
        }


class SubscriptionQuerySet(models.QuerySet):

    def get_user_subscriptions(self, user_id: int | None = None):
        latest_sub = Subscription.objects.filter(user_id=OuterRef("user_id")).values(
            "id"
        )[:1]
        q = Q(id__in=Subquery(latest_sub))
        if user_id is not None:
            q &= Q(user_id=user_id)
        return self.filter(q)

    def latest_for_user_and_client(
        self,
        user_id: int,
        client_id: int,
    ):
        return self.filter(
            user_id=user_id,
            plan__client_id=client_id,
            start_at__isnull=False,
        ).first()


class Subscription(models.Model):
    NULL = 0
    ACTIVATED = 1
    SUSPENDED = 2
    EXPIRED = 3

    STATUSES = (
        (NULL, "NULL"),
        (ACTIVATED, "ACTIVE"),
        (SUSPENDED, "SUSPENDED"),
        (EXPIRED, "EXPIRED"),
    )

    # for PayPal is a custom id
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
    # for better and easier handling on webhooks
    active_processor = models.ForeignKey(
        "Processor",
        verbose_name=_("active processor"),
        related_name="subscriptions",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    # PayPal notes
    # in case of billing subscriptions - invoice id (billing agreement)
    # in case of order - order id
    external_id = models.CharField(
        _("external_id"), max_length=128, unique=True, null=True
    )
    start_at = models.DateTimeField(_("start at"), null=True, blank=True)
    end_at = models.DateTimeField(_("end at"), null=True, blank=True)
    suspended_at = models.DateTimeField(_("suspended at"), null=True, blank=True)
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
        indexes = [
            models.Index(
                fields=["user_id", "-created_at"],
                name="idx_sub_user_id_created_at",
            )
        ]

    def __str__(self):
        return f"{self.id}"

    @property
    @admin.display(
        description=_("status"),
    )
    def status(self):
        if not self.start_at:
            return self.NULL

        if self.suspended_at:
            return self.SUSPENDED

        now = timezone.now()

        if self.start_at < now and (
            (self.end_at and now < self.end_at) or not self.end_at
        ):
            return self.ACTIVATED

        return self.EXPIRED

    def get_status_display(self):
        return dict(self.STATUSES)[self.status]

    @property
    @admin.display(
        description=_("status"),
    )
    def admin_status_with_color(self):
        # status = self.status
        match (self.status):
            case self.NULL:
                return mark_safe(
                    f"<b style='color:red;'>{self.get_status_display()}</b>"
                )
            case self.SUSPENDED:
                return mark_safe(
                    f"<b style='color:orange;'>{self.get_status_display()}</b>"
                )
            case self.ACTIVATED:
                return mark_safe(
                    f"<b style='color:green;'>{self.get_status_display()}</b>"
                )
            case self.EXPIRED:
                return mark_safe(
                    f"<b style='color:red;'>{self.get_status_display()}</b>"
                )

    @property
    @admin.display(description=_("is null"), boolean=True)
    def is_null(self):
        return self.status == self.NULL

    @property
    @admin.display(description=_("is active"), boolean=True)
    def is_active(self):
        return self.status == self.ACTIVATED

    @property
    @admin.display(description=_("is suspended"), boolean=True)
    def is_suspended(self):
        return self.status == self.SUSPENDED

    @property
    @admin.display(description=_("is expired"), boolean=True)
    def is_expired(self):
        return self.status == self.EXPIRED

    @cached_property
    @admin.display(
        ordering="plan__client",
        description=_("client"),
    )
    def client(self):
        return self.plan.client if self.plan else None

    def finish(self, end_at: datetime):
        self.end_at = end_at
        self.suspended_at = None
        self.next_billing_at = None
        self.next_billing_plan = None
        self.save(
            update_fields=[
                "end_at",
                "suspended_at",
                "next_billing_at",
                "next_billing_plan",
            ]
        )

    def suspend(self, suspended_at: datetime):
        self.suspended_at = suspended_at
        self.end_at = self.next_billing_at
        self.save(update_fields=["suspended_at", "end_at"])

    def unsuspend(self):
        self.suspended_at = None
        self.end_at = None
        self.save(update_fields=["suspended_at", "end_at"])

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

    def calculate_upgrade_amount(self, upgrade_plan: Plan) -> Decimal:
        # TODO
        return Decimal(0)

    @cached_property
    def context(self):
        return {
            "start_at": self.start_at,
            "end_at": self.end_at,
            "next_billing_at": self.next_billing_at,
        }


class Invoice(models.Model):

    PENDING = 1
    CANCELED = 2
    SUCCESS = 3
    FAILURE = 4
    EXPIRED = 5

    STATUSES = (
        (PENDING, _("Pending")),
        (CANCELED, _("Canceled")),
        (SUCCESS, _("Success")),
        (FAILURE, _("Failure")),
        (EXPIRED, _("Expired")),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subscription = models.ForeignKey(
        "Subscription",
        verbose_name=_("subscription"),
        related_name="invoices",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    processor = models.ForeignKey(
        "Processor",
        verbose_name=_("processor"),
        related_name="invoices",
        on_delete=models.CASCADE,
    )
    # PayPal notes
    # in case of billing subscriptions - sale_id for link
    # in case of order - empty
    external_id = models.CharField(
        _("external_id"), max_length=128, unique=True, null=True
    )
    amount = models.DecimalField(_("amount"), max_digits=16, decimal_places=2)
    currency = models.CharField(
        _("currency"), max_length=3, default=settings.DEFAULT_CURRENCY
    )
    status = models.PositiveIntegerField(_("status"), choices=STATUSES, default=PENDING)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("invoice")
        verbose_name_plural = _("invoices")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pk} ({self.get_status_display()})"

    @property
    def expired_at(self):
        return self.created_at + timedelta(days=3)

    @cached_property
    def context(self):
        return {
            "amount": self.amount,
            "currency": self.currency,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


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
        return build_full_path(path)

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

    def create_checkout_url(
        self, custom_id: str, amount: Decimal, return_url: str, cancel_url: str
    ):
        provider = self.get_provider()
        payload = provider.generate_checkout_data(
            custom_id,
            amount,
            return_url,
            cancel_url,
        )
        return payload.get("url")

    def create_subscription_url(
        self, custom_id: str, external_plan_id: str, return_url: str, cancel_url: str
    ):
        provider = self.get_provider()
        payload = provider.generate_subscription_data(
            custom_id,
            external_plan_id,
            return_url,
            cancel_url,
        )
        return payload.get("url") if payload else None

    def create_change_plan_url(
        self,
        external_subscription_id: str,
        external_plan_id: str,
        return_url: str,
        cancel_url: str,
    ):
        provider = self.get_provider()
        payload = provider.generate_change_subscription_data(
            external_subscription_id,
            external_plan_id,
            return_url,
            cancel_url,
        )
        return payload.get("url") if payload else None

    def activate_subscription(
        self,
        external_invoice_id: str,
        reason: str,
    ):
        provider = self.get_provider()
        provider.activate_subscription(
            external_invoice_id,
            reason,
        )

    def deactivate_subscription(
        self,
        external_invoice_id: str,
        reason: str,
    ):
        provider = self.get_provider()
        provider.deactivate_subscription(
            external_invoice_id,
            reason,
            suspend=True,  # TODO: Add flag to processor model
        )

    def approve_order(self, external_order_id: str):
        provider = self.get_provider()
        provider.approve_order(external_order_id)

    @cached_property
    def context(self):
        return {
            "type": self.get_type_display(),
        }
