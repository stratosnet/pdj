from django.contrib import admin

from .models import (
    Token,
    Client,
    SSOUser,
)


@admin.register(Token)
class TokenAdmin(admin.ModelAdmin):
    list_display = ["client__name", "key", "created_at", "is_active"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("client")


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ["name", "created_at", "updated_at", "is_active"]


@admin.register(SSOUser)
class SSOUserAdmin(admin.ModelAdmin):
    list_display = ["sub", "email", "created_at"]
