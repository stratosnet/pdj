import uuid
from datetime import timedelta

from django.db import models
from django.db.models import JSONField
from django.conf import settings
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.fields import GenericRelation


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
        "core.Client",
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

    links = GenericRelation("provider.PaymentReference")

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


class Subscription(models.Model):
    user = models.ForeignKey(
        "core.SSOUser",
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

    links = GenericRelation("provider.PaymentReference")

    class Meta:
        verbose_name = _("Subscription")
        verbose_name_plural = _("Subscriptions")
        ordering = ["-created_at"]

    def __str__(self):
        return f"user: {self.user.user_id} - tier: {self.tier.tier_id}"


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
        "core.SSOUser",
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
