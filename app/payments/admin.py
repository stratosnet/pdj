from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import (
    Plan,
    Feature,
    PlanFeature,
    Invoice,
    Subscription,
    PlanProcessorLink,
    Processor,
)
from .filters import ClientListFilter


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "user",
        "plan",
        "client",
        "admin_status_with_color",
        "start_at",
        "end_at",
        "next_billing_at",
        "next_billing_plan",
        "created_at",
    ]
    fields = [
        "user",
        "plan",
        "admin_status_with_color",
        "start_at",
        "end_at",
        "next_billing_at",
        "next_billing_plan",
        "created_at",
    ]
    readonly_fields = [
        "admin_status_with_color",
        "start_at",
        "created_at",
    ]
    list_filter = ["plan__client__name", "plan"]

    def get_queryset(self, request):
        return (
            super().get_queryset(request).select_related("user", "plan", "plan__client")
        )


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "processor",
        "external_id",
        "amount",
        "currency",
        "status",
        "created_at",
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("processor")

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Processor)
class ProcessorAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "type",
        "hidden_client_id",
        "hidden_secret",
        "created_at",
    ]
    fields = [
        "id",
        "type",
        "client_id",
        "secret",
        "endpoint_secret",
        "webhook_url",
        "is_sandbox",
        "is_enabled",
    ]
    readonly_fields = ["id", "webhook_url"]


class FeatureInline(admin.TabularInline):
    model = Feature.plans.through


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    inlines = (FeatureInline,)
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


@admin.register(Feature)
class FeatureAdmin(admin.ModelAdmin):
    list_display = ["name", "description", "created_at"]


@admin.register(PlanFeature)
class PlanFeatureAdmin(admin.ModelAdmin):
    list_display = ["id", "plan", "feature", "created_at"]
    list_filter = ["plan__name", "feature__name"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("plan", "feature")


@admin.register(PlanProcessorLink)
class PlanProcessorLinkAdmin(admin.ModelAdmin):
    list_display = [
        "id",
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
