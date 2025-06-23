from django.contrib import admin
from django.db.models import JSONField
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.contrib.admin.templatetags.admin_urls import add_preserved_filters
from django.utils.html import format_html
from django.http import HttpResponseRedirect
from urllib.parse import quote as urlquote
from django_json_widget.widgets import JSONEditorWidget

from .models import (
    Plan,
    Feature,
    PlanFeature,
    Invoice,
    Subscription,
    PlanProcessorLink,
    Processor,
    WebhookEvent,
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


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    formfield_overrides = {
        JSONField: {"widget": JSONEditorWidget(options={"mode": "code"})},
    }

    list_display = [
        "id",
        "processor",
        "event_type",
        "event_id",
        "is_processed",
        "created_at",
    ]
    fields = [
        "processor",
        "is_processed",
        "event_type",
        "event_id",
        "payload",
        "created_at",
    ]
    list_filter = ["processor__type", "event_type"]
    readonly_fields = [
        "processor",
        "is_processed",
        "event_type",
        "event_id",
        "created_at",
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("processor")

    def has_add_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        messages.error(request, _("Webhook events cannot be modified."))

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["show_save_and_continue"] = False
        extra_context["show_save"] = False
        return super().changeform_view(request, object_id, form_url, extra_context)


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


class ProcessorInline(admin.TabularInline):
    model = Plan.processors.through
    fields = ["processor", "external_id", "synced_at"]
    readonly_fields = ["external_id", "synced_at"]


class FeatureInline(admin.TabularInline):
    model = Feature.plans.through


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    change_form_template = "admin/payments/plan/change_form.html"
    inlines = (
        ProcessorInline,
        FeatureInline,
    )
    list_display = [
        "name",
        "code",
        "client",
        "duration",
        "price",
        "created_at",
        "is_recurring",
        "is_enabled",
        "is_default",
        "position",
    ]
    list_filter = [ClientListFilter, "is_recurring", "is_enabled"]
    ordering = ["position"]

    def get_readonly_fields(self, request, obj=...):
        readonly_fields = super().get_readonly_fields(request, obj)
        if obj and obj.pk:
            return readonly_fields + ("is_recurring",)
        return readonly_fields

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("client")

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        return super().change_view(
            request, object_id, form_url, extra_context=extra_context
        )

    def response_change(self, request, obj):
        opts = self.opts
        preserved_filters = self.get_preserved_filters(request)
        preserved_qsl = self._get_preserved_qsl(request, preserved_filters)

        msg_dict = {
            "name": opts.verbose_name,
            "obj": format_html('<a href="{}">{}</a>', urlquote(request.path), obj),
        }
        if "_syncprocessorlink" in request.POST:
            obj.sync_processor_links()
            msg = format_html(
                _("Sync job added for {name} “{obj}”"),
                **msg_dict,
            )
            self.message_user(request, msg, messages.SUCCESS)
            redirect_url = request.path
            redirect_url = add_preserved_filters(
                {
                    "preserved_filters": preserved_filters,
                    "preserved_qsl": preserved_qsl,
                    "opts": opts,
                },
                redirect_url,
            )
            return HttpResponseRedirect(redirect_url)
        return super().response_change(request, obj)


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
