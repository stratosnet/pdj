import uuid
from datetime import timedelta, datetime
from decimal import Decimal, InvalidOperation

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

from core.utils import (
    mask_secret,
    generate_base_secret,
    build_full_path,
    hash_key,
)

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
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    synced_at = models.DateTimeField(
        _("synced at"),
        null=True,
        blank=True,
        help_text=_("Date and time when the link was last synced with the processor"),
    )

    class Meta:
        verbose_name = _("plan processor link")
        verbose_name_plural = _("plan processor links")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "processor"],
                name="unique_plan_processor_link",
                violation_error_message=_(
                    "This processor is already linked to the plan."
                ),
            )
        ]


class Plan(models.Model):

    class Period(models.IntegerChoices):
        DAY = 1, "DAY"
        WEEK = 2, "WEEK"
        MONTH = 3, "MONTH"
        YEAR = 4, "YEAR"

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
    is_default = models.BooleanField(
        default=False,
        verbose_name=_("is default"),
        help_text=_("Whether this plan is the default for the client"),
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
    position = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("position"),
        help_text=_("Position of the plan in the API list (lower is higher priority)"),
    )
    description = models.TextField(
        null=True,
        blank=True,
        verbose_name=_("description"),
        help_text=_("Description of a plan"),
    )
    period = models.PositiveIntegerField(
        choices=Period.choices,
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
    # TODO: Add disabled
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

    processors = models.ManyToManyField(
        "Processor",
        through="PlanProcessorLink",
        through_fields=("plan", "processor"),
        related_name="plans",
        verbose_name=_("processors"),
        help_text=_("Payment processors linked to this plan"),
    )

    class Meta:
        verbose_name = _("plan")
        verbose_name_plural = _("plans")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} (price: {self.price})"

    def sync_processor_links(self):
        from .tasks.paypal import sync_plan

        sync_plan.delay(str(self.id))

    def clean(self):
        super().clean()

        if self.is_default:
            qs = Plan.objects.filter(client=self.client, is_default=True)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError(_("Only one default plan is allowed per client."))

        if self.price == 0 and not self.is_default:
            raise ValidationError(_("Price must be a positive number."))

    @property
    @admin.display(
        ordering="period",
        description=_("Billing frequency"),
    )
    def duration(self):
        if self.is_default:
            return "-"
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


class Feature(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.CharField(
        max_length=64,
        unique=True,
        verbose_name=_("key"),
        help_text=_("Unique identifier for the feature, used in code"),
        validators=[
            RegexValidator(
                regex=r"^[a-z0-9_]+$",
                message=_(
                    "Key must contain only lowercase letters, numbers, or underscores (snake_case)"
                ),
            )
        ],
    )
    name = models.CharField(
        max_length=128, verbose_name=_("name"), help_text=_("Name of the feature")
    )
    description = models.TextField(
        null=True,
        blank=True,
        verbose_name=_("description"),
        help_text=_("Description of a feature"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    plans = models.ManyToManyField(
        "Plan",
        through="PlanFeature",
        through_fields=("feature", "plan"),
        related_name="features",
        verbose_name=_("plans"),
        help_text=_("Plans that include this feature"),
    )

    class Meta:
        verbose_name = _("feature")
        verbose_name_plural = _("features")
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class PlanFeature(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan = models.ForeignKey(
        "Plan",
        verbose_name=_("plan"),
        related_name="plan_features",
        on_delete=models.CASCADE,
    )
    feature = models.ForeignKey(
        "Feature",
        verbose_name=_("feature"),
        related_name="plan_features",
        on_delete=models.CASCADE,
    )
    value = models.CharField(
        max_length=256,
        verbose_name=_("value"),
        help_text=_("Optional value for the feature (e.g., limit, quota)"),
    )

    def clean(self):
        super().clean()

        value = self.value.strip()

        if "." not in value:
            return

        try:
            dec = Decimal(value)
        except InvalidOperation:
            raise ValidationError({"value": _("Value must be a valid decimal number.")})

        digits = dec.as_tuple().digits
        exponent = dec.as_tuple().exponent

        digits_count = len(digits)
        decimal_places = abs(exponent) if exponent < 0 else 0

        if digits_count > 16 or decimal_places > 2:
            raise ValidationError(
                {
                    "value": _(
                        "Decimal value must have at most 16 digits and 2 decimal places."
                    )
                }
            )

        self.value = str(dec)

    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("plan feature")
        verbose_name_plural = _("plan features")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "feature"],
                name="unique_plan_feature",
                violation_error_message=_(
                    "This feature is already linked to the plan."
                ),
            )
        ]

    def __str__(self):
        return f"{self.plan.name} - {self.feature.name}"


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
        *,
        include_uninitialized: bool = True,
    ):
        q = Q(
            user_id=user_id,
            plan__client_id=client_id,
        )
        if include_uninitialized:
            q |= Q(start_at__isnull=True)
        return self.filter(q).first()


class Subscription(models.Model):

    class Status(models.IntegerChoices):
        NULL = 0, "NULL"
        ACTIVATED = 1, "ACTIVE"
        SUSPENDED = 2, "SUSPENDED"
        EXPIRED = 3, "EXPIRED"

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
            return self.Status.NULL

        if self.suspended_at:
            return self.Status.SUSPENDED

        now = timezone.now()

        if self.start_at < now and (
            (self.end_at and now < self.end_at) or not self.end_at
        ):
            return self.Status.ACTIVATED

        return self.Status.EXPIRED

    def get_status_display(self):
        return dict([(e.value, e.name) for e in Subscription.Status])[self.status]

    @property
    @admin.display(
        description=_("status"),
    )
    def admin_status_with_color(self):
        # status = self.status
        match (self.status):
            case self.Status.NULL:
                return mark_safe(
                    f"<b style='color:red;'>{self.get_status_display()}</b>"
                )
            case self.Status.SUSPENDED:
                return mark_safe(
                    f"<b style='color:orange;'>{self.get_status_display()}</b>"
                )
            case self.Status.ACTIVATED:
                return mark_safe(
                    f"<b style='color:green;'>{self.get_status_display()}</b>"
                )
            case self.Status.EXPIRED:
                return mark_safe(
                    f"<b style='color:red;'>{self.get_status_display()}</b>"
                )

    @property
    @admin.display(description=_("is null"), boolean=True)
    def is_null(self):
        return self.status == self.Status.NULL

    @property
    @admin.display(description=_("is active"), boolean=True)
    def is_active(self):
        return self.status == self.Status.ACTIVATED

    @property
    @admin.display(description=_("is suspended"), boolean=True)
    def is_suspended(self):
        return self.status == self.Status.SUSPENDED

    @property
    @admin.display(description=_("is expired"), boolean=True)
    def is_expired(self):
        return self.status == self.Status.EXPIRED

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
            case Plan.Period.DAY:
                return self.start_at + timedelta(days=1 * self.plan.term)
            case Plan.Period.WEEK:
                return self.start_at + timedelta(days=7 * self.plan.term)
            case Plan.Period.MONTH:
                return self.start_at + timedelta(days=30 * self.plan.term)
            case Plan.Period.YEAR:
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

    class Status(models.IntegerChoices):
        PENDING = 1, _("Pending")
        CANCELED = 2, _("Canceled")
        SUCCESS = 3, _("Success")
        FAILURE = 4, _("Failure")
        EXPIRED = 5, _("Expired")
        REFUNDED = 6, _("Refunded")

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
    status = models.PositiveIntegerField(
        _("status"), choices=Status.choices, default=Status.PENDING
    )
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


class WebhookEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    processor = models.ForeignKey(
        "Processor",
        verbose_name=_("processor"),
        related_name="webhook_events",
        on_delete=models.CASCADE,
    )
    event_type = models.CharField(
        _("event type"),
        max_length=128,
        help_text=_("Type of the webhook event (e.g., payment.completed)"),
    )
    event_id = models.CharField(_("event id"), max_length=128)
    created_at = models.DateTimeField(
        _("created at"), auto_now_add=True, help_text=_("Date and time of the event")
    )
    payload = models.JSONField(
        _("payload"),
        help_text=_("The JSON payload of the webhook event"),
    )
    is_processed = models.BooleanField(
        default=False,
        verbose_name=_("is processed"),
        help_text=_("Indicates if the webhook event has been processed"),
    )

    class Meta:
        verbose_name = _("webhook event")
        verbose_name_plural = _("webhook events")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["processor", "event_type", "event_id"],
                name="unique_webhook_event",
                violation_error_message=_("This event has already been processed."),
            )
        ]


class Processor(models.Model):

    class Type(models.TextChoices):
        PAYPAL = "paypal", _("PayPal")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField(
        max_length=20,
        choices=Type.choices,
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
        if self.type == Processor.Type.PAYPAL:
            return PayPalClient(
                client_id=self.client_id,
                client_secret=self.secret,
                is_sandbox=self.is_sandbox,
            )

        raise NotImplementedError("provider not set")

    def create_checkout_url(
        self,
        custom_id: str,
        amount: Decimal,
        return_url: str | None,
        cancel_url: str | None,
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
        self,
        custom_id: str,
        external_plan_id: str,
        return_url: str | None,
        cancel_url: str | None,
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
        return_url: str | None,
        cancel_url: str | None,
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
    def get_subscription_details(
            self,
            id,
    ):
        provider = self.get_provider()
        return provider.get_subscription_details(
            id
        )

    def approve_order(self, external_order_id: str):
        provider = self.get_provider()
        provider.approve_order(external_order_id)

    def refund_payment(self, external_payment_id: str):
        provider = self.get_provider()
        provider.refund_payment(external_payment_id)

    @cached_property
    def context(self):
        return {
            "type": self.get_type_display(),
        }


class PaymentUrlCacheManager(models.Manager):

    def get_cache_url(
        self,
        type: "PaymentUrlCache.Type",
        raw_key: str,
        *,
        processor_id: str | None = None,
    ):
        c = self.filter(
            type=type, key=hash_key(raw_key), processor_id=processor_id
        ).first()
        if c and not c.is_expired:
            return c.url

    def create_with_expiration(
        self,
        type: "PaymentUrlCache.Type",
        raw_key: str,
        url: str,
        *,
        processor_id: str | None = None,
        expires_in: timedelta = timedelta(seconds=settings.CACHE_PROCESSOR_URL_TIMEOUT),
    ):
        return self.create(
            type=type,
            key=hash_key(raw_key),
            processor_id=processor_id,
            url=url,
            expired_at=timezone.now() + expires_in,
        )

    def invalidate_cache(
        self,
        type: "PaymentUrlCache.Type",
        raw_key: str,
    ):
        return self.filter(type=type, key=hash_key(raw_key)).delete()

    def invalidate_subscription_cache(
        self,
        subscription_id: uuid.UUID,
    ):
        return self.invalidate_cache(
            type=PaymentUrlCache.Type.SUBSCRIBE,
            raw_key=f"{subscription_id}",
        )

    def invalidate_change_plan_cache(
        self,
        subscription_id: uuid.UUID,
        plan_id: uuid.UUID,
    ):
        return self.invalidate_cache(
            type=PaymentUrlCache.Type.CHANGE_PLAN,
            raw_key=f"{subscription_id}_{plan_id}",
        )

    def get_subscription_cache_url(
        self,
        subscription_id: uuid.UUID,
        *,
        processor_id: uuid.UUID | None = None,
    ):
        return self.get_cache_url(
            type=PaymentUrlCache.Type.SUBSCRIBE,
            raw_key=f"{subscription_id}",
            processor_id=processor_id,
        )

    def get_change_plan_cache_url(
        self,
        subscription_id: uuid.UUID,
        plan_id: uuid.UUID,
        *,
        processor_id: uuid.UUID | None = None,
    ):
        return self.get_cache_url(
            type=PaymentUrlCache.Type.CHANGE_PLAN,
            raw_key=f"{subscription_id}_{plan_id}",
            processor_id=processor_id,
        )

    def create_subscription_cache(
        self,
        subscription_id: uuid.UUID,
        url: str,
        *,
        processor_id: uuid.UUID | None = None,
    ):
        return self.create_with_expiration(
            type=PaymentUrlCache.Type.SUBSCRIBE,
            raw_key=f"{subscription_id}",
            url=url,
            processor_id=processor_id,
        )

    def create_change_plan_cache(
        self,
        subscription_id: uuid.UUID,
        plan_id: uuid.UUID,
        url: str,
        *,
        processor_id: uuid.UUID | None = None,
    ):
        return self.create_with_expiration(
            type=PaymentUrlCache.Type.CHANGE_PLAN,
            raw_key=f"{subscription_id}_{plan_id}",
            url=url,
            processor_id=processor_id,
        )


class PaymentUrlCache(models.Model):

    class Type(models.TextChoices):
        SUBSCRIBE = "subscribe", _("Subscribe")
        CHANGE_PLAN = "changeplan", _("Change Plan")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField(
        max_length=64,
        choices=Type.choices,
        verbose_name=_("type"),
        help_text=_("Type of the cached URL"),
    )
    key = models.CharField(
        max_length=255,
        verbose_name=_("key"),
        help_text=_("Unique key for the cached URL, used to identify the cache entry"),
    )
    processor = models.ForeignKey(
        "Processor",
        verbose_name=_("processor"),
        related_name="payment_url_cache",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text=_("The payment processor for which the URL is cached"),
    )
    url = models.URLField(
        verbose_name=_("URL"),
        help_text=_("The cached URL for the payment processor"),
    )
    expired_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    objects = PaymentUrlCacheManager()

    class Meta:
        verbose_name = _("payment URL cache")
        verbose_name_plural = _("payment URL caches")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["type", "key"],
                name="unique_payment_url_cache",
                violation_error_message=_("This URL cache already exists."),
            )
        ]

    def __str__(self):
        return f"{self.type}:{self.key} (expires: {self.expired_at})"

    @property
    def is_expired(self):
        return timezone.now() > self.expired_at
