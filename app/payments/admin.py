from django.contrib import admin
from django.urls import reverse

from .models import (
    Plan,
    Payment,
    Subscription,
    PlanProcessorLink,
    Processor,
)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "user",
        "plan",
        "payment",
        "start_at",
        "end_at",
        "created_at",
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user", "plan", "payment")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "external_id",
        "user",
        "processor",
        "amount",
        "currency",
        "status",
        "created_at",
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user", "processor")


@admin.register(Processor)
class ProcessorAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "processor_type",
        "hidden_client_id",
        "hidden_secret",
        "created_at",
    ]
    fields = [
        "processor_type",
        "client_id",
        "secret",
        "endpoint_secret",
        "webhook_url",
        "is_sandbox",
        "is_enabled",
    ]
    readonly_fields = ["webhook_url"]


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "name",
        "client",
        "duration",
        "price",
        "is_recurring",
        "created_at",
        "is_enabled",
    ]
    list_filter = ["client__name", "is_recurring", "is_enabled"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("client")


@admin.register(PlanProcessorLink)
class PlanProcessorLinkAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "plan",
        "processor",
        "external_id",
        "created_at",
    ]

    def has_change_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("plan", "processor")
