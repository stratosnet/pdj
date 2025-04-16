from django.contrib import admin
from django.contrib.auth.admin import (
    UserAdmin as BaseUserAdmin,
    GroupAdmin as BaseGroupAdmin,
)
from django.contrib.auth.models import Group
from django.utils.translation import gettext_lazy as _

from .models import (
    Client,
    User,
    SSOIdentity,
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name")}),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "usable_password", "password1", "password2"),
            },
        ),
    )

    list_display = ("email", "first_name", "last_name", "is_staff")
    list_filter = ("is_staff", "is_superuser", "is_active", "groups")
    search_fields = ("first_name", "last_name", "email")
    ordering = ("email",)


admin.site.unregister(Group)


class GroupAdmin(BaseGroupAdmin):
    pass


class GroupMeta:
    proxy = True
    app_label = User._meta.app_label


group_model = type("Group", (Group,), {"__module__": "", "Meta": GroupMeta})
admin.site.register(group_model, GroupAdmin)


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
        "home_url",
        "return_url",
        "cancel_url",
        "is_enabled",
        "created_at",
    ]
    readonly_fields = ["client_id", "client_secret", "sku_prefix", "created_at"]

    def get_fields(self, request, obj=None):
        fields = super().get_fields(request, obj)
        if obj is not None:
            return fields

        fields = fields[:]
        fields.remove("client_id")
        fields.remove("client_secret")
        return fields


@admin.register(SSOIdentity)
class SSOIdentityAdmin(admin.ModelAdmin):
    list_display = ["sub", "user", "created_at"]
    fields = ["sub", "user", "created_at"]
    readonly_fields = ["created_at"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user")
