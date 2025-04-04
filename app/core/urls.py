"""
URL configuration for core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

import logging

from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from django.utils.translation import gettext_lazy as _

from .api import api as ninja_api

logger = logging.getLogger(__name__)

urlpatterns = []

urlpatterns += [
    path("api/", ninja_api.urls),
]

if settings.DEBUG_TOOLBAR_ENABLED:
    try:
        from debug_toolbar.toolbar import debug_toolbar_urls

        urlpatterns += debug_toolbar_urls()
    except ModuleNotFoundError as e:
        logger.warning(e.args[0])

urlpatterns += [
    path("admin/", admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# django admin title replacement
admin.site.site_header = _("Payment service")
