from django.contrib import admin

from .models import (
    Plan,
    Order,
    Subscription,
)

admin.site.register(Order)
admin.site.register(Subscription)


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
