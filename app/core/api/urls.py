from django.urls import path
from ._base import api

from . import routes

urlpatterns = [
    path("api/", api.urls),
]
