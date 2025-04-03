import logging

from django.conf import settings
from django.http import HttpRequest

from ninja.security import HttpBearer

from fief_client import Fief
from fief_client.client import (
    FiefAccessTokenInvalid,
    FiefAccessTokenExpired,
    FiefAccessTokenMissingScope,
)
from .._base import api
from core.models import SSOUser


fief_client = Fief(
    settings.OIDC_ISSUER_URI,
    settings.OIDC_CLIENT_ID,
    settings.OIDC_CLIENT_SECRET,
)


logger = logging.getLogger(__name__)


@api.exception_handler(FiefAccessTokenInvalid)
def on_invalid_token(request, exc):
    return api.create_response(request, {"detail": "Invalid access token"}, status=401)


@api.exception_handler(FiefAccessTokenExpired)
def on_expired_token(request, exc):
    return api.create_response(request, {"detail": "Expired access token"}, status=401)


@api.exception_handler(FiefAccessTokenMissingScope)
def on_missing_token(request, exc):
    return api.create_response(
        request, {"detail": "Missing required scope"}, status=401
    )


class OIDCBearer(HttpBearer):
    def authenticate(self, request: HttpRequest, token: str):
        access_token_info = fief_client.validate_access_token(
            token, required_scope=["openid"]
        )
        print("access_token_info", access_token_info)
        sub = access_token_info.get("id")
        if not sub:
            return

        user, _ = SSOUser.objects.get_or_create(sub=sub)
        request.sso = user
        return user


oidc_auth = OIDCBearer()
