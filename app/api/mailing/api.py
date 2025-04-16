import logging

from django.http import HttpRequest

from ninja import Router

from core.utils import get_value_from_timestamp_token
from accounts.models import User

from .schemas import (
    ErrorSchema,
)


logger = logging.getLogger(__name__)

router = Router()


@router.get(
    "/unsubscribe/{token}",
    summary="Mailing unsubscribe",
    response={200: ErrorSchema, 400: ErrorSchema},
)
def mailing_unsubscribe(request: HttpRequest, token: str):
    id, is_valid = get_value_from_timestamp_token(token)
    if not is_valid:
        return 400, {"message": "Token has been expired"}

    try:
        user = User.objects.get(pk=id, is_mailing_subscribed=True)
    except User.DoesNotExist:
        return 400, {"message": "User already unsubscribed from mailing"}

    user.is_mailing_subscribed = False
    user.save(update_fields=["is_mailing_subscribed"])

    return 200, {"message": "Successfully unsubscribed from mailing"}
