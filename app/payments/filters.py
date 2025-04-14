from django.contrib import admin
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from accounts.models import Client


class ClientListFilter(admin.SimpleListFilter):
    title = _("Client")

    parameter_name = "client__name"

    def lookups(self, request, model_admin):
        for client in Client.objects.all():
            yield (client.name, client.name)

    def queryset(self, request, queryset):
        if self.value() == None:
            return queryset

        return queryset.filter(Q(**{self.parameter_name: self.value()}))
