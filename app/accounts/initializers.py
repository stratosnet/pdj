from django.conf import settings

from core.utils import generate_sku_prefix, generate_base_secret

from .models import User, Client


class ClientInitializer:
    def initialize(self, log_func):
        if Client.objects.first():
            return

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
        log_func("Default client initialized")


class UserInitializer:
    def initialize(self, log_func):
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
            log_func("Main user initialized")
