from django.db import models
from django.utils.translation import gettext_lazy as _

from core.utils import generate_sku_prefix, generate_client_key


class Client(models.Model):

    name = models.CharField(
        max_length=20,
        verbose_name=_("Name"),
        help_text=_("Client's full name or company name"),
    )
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("Description"),
        help_text=_("Additional information about the client"),
    )

    client_id = models.CharField(
        _("Client ID"),
        max_length=40,
        unique=True,
        editable=False,
        help_text=_("Client ID"),
        default=generate_client_key,
    )
    client_secret = models.CharField(
        _("Client secret"),
        max_length=40,
        unique=True,
        editable=False,
        help_text=_("Client secret"),
        default=generate_client_key,
    )

    product_name = models.CharField(
        max_length=80,
        verbose_name=_("Product name"),
        help_text=_("Description of a product which provided by client"),
    )
    sku_prefix = models.CharField(
        max_length=4,
        blank=True,
        verbose_name=_("SKU prefix"),
        help_text=_(
            "SKU prefix for the product (if not set, will be automatically generated)"
        ),
    )
    image_url = models.URLField(
        _("image url"),
        help_text=_("The image URL for the product"),
        null=True,
        blank=True,
    )
    home_url = models.URLField(
        _("home url"),
        help_text=_("The home page URL for the product"),
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated At"))
    is_enabled = models.BooleanField(
        default=False,
        verbose_name=_("Is Active"),
        help_text=_("Designates whether this client is active"),
    )

    class Meta:
        verbose_name = _("Client")
        verbose_name_plural = _("Clients")
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def clean(self):
        if not self.sku_prefix:
            self.sku_prefix = generate_sku_prefix()
        else:
            self.sku_prefix = self.sku_prefix.capitalize()


class SSOUser(models.Model):

    sub = models.UUIDField(
        primary_key=True,
        unique=True,
        editable=False,
        verbose_name=_("Subject Identifier"),
        help_text=_("Unique identifier from SSO provider"),
    )
    email = models.EmailField(blank=True, null=True, verbose_name=_("Email"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))

    class Meta:
        verbose_name = _("SSO User")
        verbose_name_plural = _("SSO Users")
        ordering = ["-created_at"]

    def __str__(self):
        return self.sub.hex
