from django.contrib import admin

from .models import (
    Client,
    SSOUser,
)


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ["name", "sku_prefix", "created_at", "updated_at", "is_enabled"]
    fields = [
        "name",
        "description",
        "product_name",
        "sku_prefix",
        "client_id",
        "client_secret",
        "image_url",
        "home_url",
        "is_enabled",
        "created_at",
    ]
    readonly_fields = ["client_id", "client_secret", "created_at"]

    def get_fields(self, request, obj=None):
        fields = super().get_fields(request, obj)
        if obj is not None:
            return fields

        fields = fields[:]
        fields.remove("client_id")
        fields.remove("client_secret")
        return fields


@admin.register(SSOUser)
class SSOUserAdmin(admin.ModelAdmin):
    list_display = ["sub", "email", "created_at"]
