from ninja import NinjaAPI

from .authenticators import (
    OIDCBearer,
    reg_oidc_exceptions,
)


api = NinjaAPI(
    auth=OIDCBearer(),
)
api.add_router("/payments/", "payments.api.router")

reg_oidc_exceptions(api)
