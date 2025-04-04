from django.contrib import admin

from .models import (
    Token,
    Client,
    SSOUser,
)


@admin.register(Token)
class TokenAdmin(admin.ModelAdmin):
    list_display = ["client__name", "key", "created_at", "is_enabled"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("client")


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ["name", "sku_prefix", "created_at", "updated_at", "is_enabled"]


@admin.register(SSOUser)
class SSOUserAdmin(admin.ModelAdmin):
    list_display = ["sub", "email", "created_at"]
