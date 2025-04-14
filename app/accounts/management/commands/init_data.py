import secrets
import base64

from django.core.management.base import BaseCommand
from django.db import transaction
from django.core.files.base import ContentFile
from django.contrib.auth import get_user_model
from django.conf import settings

from admin_interface.models import Theme

from accounts.models import Client
from payments.models import Processor
from core.utils import generate_sku_prefix, generate_base_secret


def generate_default_theme():
    data = {
        "active": True,
        "collapsible_stacked_inlines": False,
        "collapsible_stacked_inlines_collapsed": False,
        "collapsible_tabular_inlines": False,
        "collapsible_tabular_inlines_collapsed": False,
        "css_delete_button_background_color": "#BA2121",
        "css_delete_button_background_hover_color": "#A41515",
        "css_delete_button_text_color": "#FFFFFF",
        "css_generic_link_active_color": "#8375E0",
        "css_generic_link_color": "#463394",
        "css_generic_link_hover_color": "#6A4EE1",
        "css_header_background_color": "#463394",
        "css_header_link_color": "#FFFFFF",
        "css_header_link_hover_color": "#9F8EFF",
        "css_header_text_color": "#6A4EE1",
        "css_module_background_color": "#6F52EC",
        "css_module_background_selected_color": "#FFFFCC",
        "css_module_link_color": "#FFFFFF",
        "css_module_link_hover_color": "#9F8EFF",
        "css_module_link_selected_color": "#FFFFFF",
        "css_module_rounded_corners": True,
        "css_module_text_color": "#FFFFFF",
        "css_save_button_background_color": "#352771",
        "css_save_button_background_hover_color": "#463394",
        "css_save_button_text_color": "#FFFFFF",
        "env_color": "#E74C3C",
        "env_name": "",
        "env_visible_in_favicon": True,
        "env_visible_in_header": True,
        "foldable_apps": True,
        "form_pagination_sticky": False,
        "form_submit_sticky": False,
        "language_chooser_active": True,
        "language_chooser_control": "default-select",
        "language_chooser_display": "code",
        "list_filter_dropdown": True,
        "list_filter_highlight": True,
        "list_filter_removal_links": False,
        "list_filter_sticky": True,
        "logo_color": "#FFFFFF",
        "logo_max_height": 40,
        "logo_max_width": 200,
        "logo_visible": True,
        "name": settings.PDJ_TITLE_NAME,
        "recent_actions_visible": True,
        "related_modal_active": True,
        "related_modal_background_color": "#000000",
        "related_modal_background_opacity": "0.3",
        "related_modal_close_button_visible": True,
        "related_modal_rounded_corners": True,
        "show_fieldsets_as_tabs": False,
        "show_inlines_as_tabs": False,
        "title": "Pay DJ",
        "title_color": "#F5DD5D",
        "title_visible": True,
    }
    theme = Theme.objects.get_active()
    if theme.name == settings.PDJ_TITLE_NAME:
        return False

    for k, v in data.items():
        setattr(theme, k, v)

    favicon_img_data = "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"
    logo_img_data = "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"
    theme.favicon.save(
        "dj_favicon.png", ContentFile(base64.b64decode(favicon_img_data)), save=True
    )
    theme.logo.save(
        "dj_logo.png", ContentFile(base64.b64decode(logo_img_data)), save=True
    )
    theme.save()
    return True


class Command(BaseCommand):
    help = "Generate initial project data"

    @transaction.atomic
    def handle(self, *args, **options):
        is_gen = generate_default_theme()
        if is_gen:
            self.stdout.write(self.style.SUCCESS("Theme initialized"))

        User = get_user_model()
        email = (
            settings.PDJ_MAIN_USER_EMAIL.strip()
            if settings.PDJ_MAIN_USER_EMAIL
            else None
        )
        password = (
            settings.PDJ_MAIN_USER_PASSWORD.strip()
            if settings.PDJ_MAIN_USER_PASSWORD
            else None
        )
        if email and not User.objects.filter(email=email).exists():
            User.objects.create_superuser(email=email, password=password)
            self.stdout.write(self.style.SUCCESS("Main user initialized"))

        if not Client.objects.first():
            if settings.PDJ_CLIENT_ID and settings.PDJ_CLIENT_SECRET:
                client_id = settings.PDJ_CLIENT_ID
                client_secret = settings.PDJ_CLIENT_SECRET
            else:
                client_id = generate_base_secret()
                client_secret = generate_base_secret()

            Client.objects.create(
                name="Default",
                sku_prefix=generate_sku_prefix(),
                product_name="Default online product",
                client_id=client_id,
                client_secret=client_secret,
                is_enabled=True,
            )
            self.stdout.write(self.style.SUCCESS("Default client initialized"))

        if not Processor.objects.first():
            if settings.PDJ_PAYPAL_CLIENT_ID and settings.PDJ_PAYPAL_CLIENT_SECRET:
                Processor.objects.create(
                    type=Processor.PAYPAL,
                    client_id=settings.PDJ_PAYPAL_CLIENT_ID,
                    secret=settings.PDJ_PAYPAL_CLIENT_SECRET,
                    endpoint_secret=settings.PDJ_PAYPAL_ENDPOINT_SECRET,
                    is_sandbox=(
                        settings.PDJ_PAYPAL_IS_SANDBOX
                        if settings.PDJ_PAYPAL_IS_SANDBOX
                        else True
                    ),
                    is_enabled=True,
                )
                self.stdout.write(
                    self.style.SUCCESS("Default paypal processor initialized")
                )

        self.stdout.write(self.style.SUCCESS("Successfully initialized project data"))
