from django.db import models
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError

from core.utils import mask_secret

from .clients.paypal import PayPalClient


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
        verbose_name=_("Webhook Secret"),
        help_text=_("Secret used to verify webhook payloads (optional)"),
    )

    is_sandbox = models.BooleanField(
        default=True,
        verbose_name=_("Is Sandbox"),
        help_text=_("Indicates if these credentials relates to sandbox"),
    )
    is_active = models.BooleanField(
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

    def get_provider(self):
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

    class Meta:
        verbose_name = _("Payment Reference")
        verbose_name_plural = _("Payment References")
        unique_together = ("processor", "external_id")
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
        ]

    def __str__(self):
        return f"{self.processor}:{self.object_id} (ID: {self.external_id})"
