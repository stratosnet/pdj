import logging

from django.conf import settings
from django.http import HttpRequest
from django.contrib.auth import get_user_model
from django.db import transaction

from ninja.security import HttpBearer

from fief_client import Fief
from fief_client.client import (
    FiefAccessTokenInvalid,
    FiefAccessTokenExpired,
    FiefAccessTokenMissingScope,
    FiefRequestError,
)
from accounts.models import SSOIdentity

# TODO: Add fief creds check
fief_client = Fief(
    settings.OIDC_ISSUER_URI,
    settings.OIDC_CLIENT_ID,
    settings.OIDC_CLIENT_SECRET,
)


logger = logging.getLogger(__name__)


def reg_oidc_exceptions(api):
    @api.exception_handler(FiefRequestError)
    def on_invalid_token(request, exc):
        return api.create_response(request, {"detail": "Unauthorized"}, status=401)

    @api.exception_handler(FiefAccessTokenInvalid)
    def on_invalid_token(request, exc):
        return api.create_response(
            request, {"detail": "Invalid access token"}, status=401
        )

    @api.exception_handler(FiefAccessTokenExpired)
    def on_expired_token(request, exc):
        return api.create_response(
            request, {"detail": "Expired access token"}, status=401
        )

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
        User = get_user_model()

        sub = access_token_info["id"]
        try:
            user = User.objects.get(identities__sub=sub)
        except User.DoesNotExist:
            userinfo = fief_client.userinfo(token)
            email = userinfo["email"]
            sub = userinfo["sub"]

            with transaction.atomic():
                if not SSOIdentity.objects.filter(sub=sub).exists():
                    user = User.objects.select_for_update().filter(email=email).first()
                    if not user:
                        user = User.objects.create_user(email=email, password=None)
                    SSOIdentity.objects.create(sub=sub, user=user)

        return user
