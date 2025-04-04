import logging
from functools import wraps

from django.http import HttpRequest
from ninja.security import APIKeyHeader
from ninja.errors import HttpError

from accounts.models import Client

logger = logging.getLogger(__name__)


class ClientAuth(APIKeyHeader):
    param_name = "X-Client-Key"

    def authenticate(self, request, key):
        client = Client.objects.filter(
            auth_tokens__key=key, auth_tokens__is_enabled=True
        ).first()
        if client:
            request.client = client
            return key


def authenticate_client(func):
    @wraps(func)
    def wrapper(request: HttpRequest, *args, **kwargs):
        result = ClientAuth()(request)
        if not result:
            raise HttpError(401, "Invalid or missing X-Client-Key")
        return func(request, *args, **kwargs)

    return wrapper
