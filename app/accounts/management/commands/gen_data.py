import secrets

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from faker import Faker

from accounts.models import Client, Token
from payments.models import Plan, Processor
from core.utils import generate_sku_prefix


class Command(BaseCommand):
    help = "Generate initial test data"

    @transaction.atomic
    def handle(self, *args, **options):
        faker = Faker()

        client = Client.objects.create(
            name=faker.domain_name(),
            description=faker.text(40),
            product_name=faker.text(40),
            sku_prefix=generate_sku_prefix(),
            is_enabled=True,
        )
        Token.objects.create(client=client, is_enabled=True)

        Processor.objects.create(
            processor_type=Processor.PAYPAL,
            client_id=secrets.token_urlsafe(),
            secret=secrets.token_urlsafe(),
            endpoint_secret=secrets.token_urlsafe(),
            is_sandbox=True,
            is_enabled=True,
        )

        Plan.objects.create(
            client=client,
            name=faker.bothify(text="Plan Name: ????-########"),
            description=faker.text(40),
            period=Plan.MONTH,
            term=12,
            is_recurring=False,
            price=faker.pydecimal(100, 2, True, 1, 100),
            is_enabled=True,
        )

        self.stdout.write(self.style.SUCCESS("Successfully generated fake data"))
