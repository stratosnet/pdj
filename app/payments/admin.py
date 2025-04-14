from django.contrib import admin
from django.urls import reverse

from .models import (
    Plan,
    Payment,
    Subscription,
    PlanProcessorLink,
    Processor,
)
from .filters import ClientListFilter


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = [
        "pk",
        "user",
        "plan",
        "client",
        "payment",
        "is_active",
        "start_at",
        "end_at",
        "next_billing_at",
        "next_billing_plan",
        "created_at",
    ]
    fields = [
        "user",
        "plan",
        "payment",
        "is_active",
        "start_at",
        "end_at",
        "next_billing_at",
        "next_billing_plan",
        "created_at",
    ]
    readonly_fields = [
        "is_active",
        "payment",
        "start_at",
        "created_at",
    ]
    list_filter = ["plan__client__name", "plan"]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("user", "plan", "plan__client", "payment")
        )


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = [
        "pk",
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

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Processor)
class ProcessorAdmin(admin.ModelAdmin):
    list_display = [
        "type",
        "hidden_client_id",
        "hidden_secret",
        "created_at",
    ]
    fields = [
        "type",
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
        "name",
        "code",
        "client",
        "duration",
        "price",
        "is_recurring",
        "created_at",
        "is_enabled",
    ]
    list_filter = [ClientListFilter, "is_recurring", "is_enabled"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("client")


@admin.register(PlanProcessorLink)
class PlanProcessorLinkAdmin(admin.ModelAdmin):
    list_display = [
        "pk",
        "plan",
        "processor",
        "external_id",
        "created_at",
    ]

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("plan", "processor")
