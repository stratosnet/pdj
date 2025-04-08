import logging
from functools import wraps

from django.http import HttpRequest
from ninja.errors import HttpError

from accounts.models import Client

logger = logging.getLogger(__name__)


CLIENT_ID_PARAM_NAME = "X-Client-ID"
CLIENT_SECRET_PARAM_NAME = "X-Client-Secret"


def authenticate_client(func=None, full=True):

    def decorator(f):
        @wraps(f)
        def wrapper(request: HttpRequest, *args, **kwargs):
            client_id = request.headers.get(CLIENT_ID_PARAM_NAME)
            client_secret = request.headers.get(CLIENT_SECRET_PARAM_NAME)

            if full:
                if client_secret and client_id:
                    client = Client.objects.filter(
                        client_id=client_id, client_secret=client_secret
                    ).first()
                    if client:
                        request.client = client
                        return f(request, *args, **kwargs)

                raise HttpError(
                    401,
                    f"Invalid or missing {CLIENT_ID_PARAM_NAME}/{CLIENT_SECRET_PARAM_NAME}",
                )

            if client_id:
                client = Client.objects.filter(client_id=client_id).first()
                if client:
                    request.client = client
                    return f(request, *args, **kwargs)

            raise HttpError(401, f"Invalid or missing {CLIENT_ID_PARAM_NAME}")

        return wrapper

    if callable(func):
        return decorator(func)
    return decorator
