from django.contrib import admin
from django.contrib.admin.templatetags.admin_urls import add_preserved_filters
from django.utils.translation import gettext_lazy as _
from django.http import HttpResponseRedirect

from admin_interface.models import Theme as AITheme
from admin_interface.admin import ThemeAdmin as AIThemeAdmin

from .models import Theme, EmailTemplate

from accounts.models import Client
from payments.models import Plan


admin.site.unregister(AITheme)


@admin.register(Theme)
class ThemeAdmin(AIThemeAdmin):
    pass


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    change_form_template = "customizations/email_template_change_form.html"
    list_display = [
        "type",
        "subject",
    ]
    fields = [
        "type",
        "subject",
        "content",
    ]
    readonly_fields = ["type"]

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False

    def response_change(self, request, obj):
        if "_testsend" in request.POST:
            # fake data
            theme = Theme.objects.get_active()
            client = Client(name="Test client")
            plan = Plan(
                client=client, name="Test plan", period=Plan.MONTH, term=1, price=10
            )

            context = {
                "user": request.user.context,
                "theme": theme.context,
                "client": client.context,
                "plan": plan.context,
            }

            obj.send(request.user.email, context)

            self.message_user(
                request, _(f"Test email has been sent to '{request.user.email}'")
            )
            opts = self.opts
            preserved_filters = self.get_preserved_filters(request)
            preserved_qsl = self._get_preserved_qsl(request, preserved_filters)
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
