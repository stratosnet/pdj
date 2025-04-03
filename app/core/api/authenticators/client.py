import logging

from ninja.security import APIKeyHeader

from core.models import Client

logger = logging.getLogger(__name__)


class ClientAuth(APIKeyHeader):
    param_name = "X-Client-Key"

    def authenticate(self, request, key):
        client = Client.objects.filter(
            auth_tokens__key=key, auth_tokens__is_active=True
        ).first()
        if client:
            request.client = client
            return key


client_auth = ClientAuth()
