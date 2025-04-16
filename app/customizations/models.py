from typing import Any
import uuid

import orjson

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils.functional import cached_property

from admin_interface.models import Theme as AITheme
from tinymce.models import HTMLField

from core.utils import build_full_path
from core.jinja2 import get_jinja2_env
from .tasks import send_template


class Theme(AITheme):
    class Meta:
        proxy = True

    @cached_property
    def context(self):
        return {
            "name": self.name,
            "active": self.active,
            "title": self.title,
            "title_color": self.title_color,
            "title_visible": self.title_visible,
            "logo_url": build_full_path(self.logo.url) if self.logo else "",
            "logo_color": self.logo_color,
            "logo_max_width": self.logo_max_width,
            "logo_max_height": self.logo_max_height,
            "logo_visible": self.logo_visible,
            "favicon": self.favicon.url if self.favicon else "",
            "css_header_background_color": self.css_header_background_color,
            "css_header_text_color": self.css_header_text_color,
            "css_header_link_color": self.css_header_link_color,
            "css_header_link_hover_color": self.css_header_link_hover_color,
            "css_module_background_color": self.css_module_background_color,
            "css_module_background_selected_color": self.css_module_background_selected_color,
            "css_module_text_color": self.css_module_text_color,
            "css_module_link_color": self.css_module_link_color,
            "css_module_link_selected_color": self.css_module_link_selected_color,
            "css_module_link_hover_color": self.css_module_link_hover_color,
            "css_module_rounded_corners": self.css_module_rounded_corners,
            "css_generic_link_color": self.css_generic_link_color,
            "css_generic_link_hover_color": self.css_generic_link_hover_color,
            "css_generic_link_active_color": self.css_generic_link_active_color,
            "css_save_button_background_color": self.css_save_button_background_color,
            "css_save_button_background_hover_color": self.css_save_button_background_hover_color,
            "css_save_button_text_color": self.css_save_button_text_color,
            "css_delete_button_background_color": self.css_delete_button_background_color,
            "css_delete_button_background_hover_color": self.css_delete_button_background_hover_color,
            "css_delete_button_text_color": self.css_delete_button_text_color,
        }


class EmailTemplateQuerySet(models.QuerySet):
    def get_by_type(self, type: int):
        return self.filter(type=type).first()


class EmailTemplate(models.Model):
    BASE = "base"
    SUBSCRIPTION_ACTIVATED = "subscription_activated"  # not implemented
    SUBSCRIPTION_RENEWAL = "subscription_renewal"  # not implemented
    SUBSCRIPTION_CANCELED = "subscription_canceled"
    SUBSCRIPTION_EXPIRED = "subscription_expired"  # not implemented
    SUBSCRIPTION_UPDATED = "subscription_updated"  # not implemented
    PAYMENT_SUCCESS = "payment_success"
    PAYMENT_FAILED = "payment_failed"  # not implemented
    TRIAL_ENDING = "trial_ending"  # not implemented
    REFUNDED = "refunded"  # not implemented

    TYPES = (
        (BASE, BASE),
        (PAYMENT_SUCCESS, PAYMENT_SUCCESS),
        (SUBSCRIPTION_CANCELED, SUBSCRIPTION_CANCELED),
        (SUBSCRIPTION_RENEWAL, SUBSCRIPTION_RENEWAL),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField(
        max_length=64,
        choices=TYPES,
        verbose_name=_("type"),
    )
    subject = models.TextField(max_length=988, verbose_name=_("subject"))
    content = HTMLField(
        verbose_name=_("content"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("created at"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("updated at"))

    objects = EmailTemplateQuerySet.as_manager()

    class Meta:
        verbose_name = _("email template")
        verbose_name_plural = _("email templates")
        ordering = ["type"]

    def __str__(self):
        return f"{self.get_type_display()}: {self.subject}"

    def send(self, to: str, context: dict[str, Any] | None = None):
        context_str = None
        if context:
            context_str = orjson.dumps(context)

        send_template.apply_async(args=(self.type, to, context_str))

    def validate_template(self, context: dict[str, Any] | None = None):
        self.render_subject(context)
        self.render_content(context)

    def render_subject(self, context: dict[str, Any]):
        return get_jinja2_env().from_string(self.subject).render(context)

    def render_content(self, context: dict[str, Any]):
        types = dict(self.TYPES)
        templates = {types[self.type]: self.content}
        if self.type != EmailTemplate.BASE:
            base_template = EmailTemplate.objects.get_by_type(EmailTemplate.BASE)
            if base_template:
                templates[types[base_template.type]] = base_template.content

        env = get_jinja2_env(templates)
        template = env.get_template(types[self.type])
        return template.render(**context)
