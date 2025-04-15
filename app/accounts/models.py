import uuid

from django.conf import settings
from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.contrib.auth.hashers import make_password
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from core.utils import generate_sku_prefix, generate_base_secret


class Client(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(
        max_length=20,
        verbose_name=_("name"),
        help_text=_("client's full name or company name"),
    )
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("description"),
        help_text=_("additional information about the client"),
    )

    client_id = models.CharField(
        _("client ID"),
        max_length=40,
        unique=True,
        editable=False,
        help_text=_("client ID"),
        default=generate_base_secret,
    )
    client_secret = models.CharField(
        _("client secret"),
        max_length=40,
        unique=True,
        editable=False,
        help_text=_("client secret"),
        default=generate_base_secret,
    )

    product_name = models.CharField(
        max_length=80,
        verbose_name=_("product name"),
        help_text=_("description of a product which provided by client"),
    )
    sku_prefix = models.CharField(
        max_length=4,
        blank=True,
        verbose_name=_("SKU prefix"),
        default=generate_sku_prefix,
        help_text=_(
            "SKU prefix for the product (will be automatically generated if skipped)"
        ),
    )
    return_url = models.URLField(
        verbose_name=_("кeturn URL"),
        help_text=_(
            "the URL of the product page where users are redirected after completing a payment."
        ),
        null=True,
        blank=True,
    )

    cancel_url = models.URLField(
        verbose_name=_("Cancel URL"),
        help_text=_(
            "the URL of the product page where users are redirected if they cancel the payment. If not provided, the Return URL will be used."
        ),
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated At"))
    is_enabled = models.BooleanField(
        default=False,
        verbose_name=_("is enabled"),
        help_text=_("designates whether this client is active"),
    )

    class Meta:
        verbose_name = _("client")
        verbose_name_plural = _("clients")
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def clean(self):
        if not self.sku_prefix:
            self.sku_prefix = generate_sku_prefix()
        else:
            self.sku_prefix = self.sku_prefix.upper()

    @cached_property
    def product_id(self):
        return f"{self.sku_prefix}-{self.pk}"

    @cached_property
    def context(self):
        return {
            "name": self.name,
        }


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("The given email must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.password = make_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(_("email address"), unique=True)
    username = None
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")

    def __str__(self):
        return self.email

    @cached_property
    def sub(self):
        sso = self.sso_identities.first()
        if sso:
            return str(sso.sub)

    @cached_property
    def context(self):
        return {
            "email": self.email,
        }


class SSOIdentity(models.Model):
    sub = models.UUIDField(
        primary_key=True,
        unique=True,
        verbose_name=_("subject identifier"),
        help_text=_("unique identifier from sso provider"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("user"),
        on_delete=models.CASCADE,
        related_name="sso_identities",
        unique=True,
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("created at"))

    class Meta:
        verbose_name = _("SSO identity")
        verbose_name_plural = _("SSO identities")
        ordering = ["-created_at"]

    def __str__(self):
        return self.sub.hex
