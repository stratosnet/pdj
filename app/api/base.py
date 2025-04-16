from django.conf import settings
from ninja import NinjaAPI

from .authenticators import (
    reg_oidc_exceptions,
)

from .mailing.api import router as mailing_router
from .users.api import router as users_router
from .plans.api import router as plans_router
from .subscriptions.api import router as subscriptions_router
from .webhooks.api import router as webhooks_router


api = NinjaAPI(title=f"{settings.PDJ_TITLE_NAME} API", csrf=False)

api.add_router("/mailing/", mailing_router)
api.add_router("/users/", users_router)
api.add_router("/plans/", plans_router)
api.add_router("/subscriptions/", subscriptions_router)
api.add_router("/webhooks/", webhooks_router)

reg_oidc_exceptions(api)
