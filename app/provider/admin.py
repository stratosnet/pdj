from django.contrib import admin

from .models import (
    Processor,
    PaymentReference,
)

admin.site.register(PaymentReference)


@admin.register(Processor)
class ProcessorAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "processor_type",
        "hidden_client_id",
        "hidden_secret",
        "created_at",
    ]
