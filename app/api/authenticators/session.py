from typing import Any
import uuid

from django.conf import settings
from django.http import HttpRequest

from ninja.security.apikey import APIKeyCookie


class SessionAuth(APIKeyCookie):
    "Reusing Django session authentication with identity capability"

    param_name: str = settings.SESSION_COOKIE_NAME

    def authenticate(self, request: HttpRequest, key: str | None) -> Any | None:
        if request.user.is_authenticated:
            return request.user

        return None
