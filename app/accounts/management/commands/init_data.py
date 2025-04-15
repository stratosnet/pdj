import importlib

from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth import get_user_model
from django.conf import settings

from accounts.models import Client
from payments.models import Processor
from core.utils import generate_sku_prefix, generate_base_secret


class Command(BaseCommand):
    help = "Generate initial project data"

    @transaction.atomic
    def handle(self, *args, **options):
        def log_func(text: str, as_error: bool = False):
            self.stdout.write(self.style.SUCCESS(text))

        for pdj_init_mod in settings.PDJ_INITIALIZERS:
            try:
                module_name, klass_name = pdj_init_mod.rsplit(".", 1)
                initializers = importlib.import_module(module_name)
            except ModuleNotFoundError:
                log_func(f"Module '{module_name}' not found", as_error=True)
                return

            Initializer = getattr(initializers, klass_name)
            if not Initializer:
                log_func(f"Initializer '{klass_name}' not found", as_error=True)
                return

            Initializer().initialize(log_func)

        log_func("Successfully initialized project data")
