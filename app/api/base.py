from typing import Any
from django.conf import settings
from ninja import NinjaAPI
from ninja.errors import ValidationError, ValidationErrorContext

from .authenticators import (
    reg_oidc_exceptions,
)

from .mailing.api import router as mailing_router
from .users.api import router as users_router
from .plans.api import router as plans_router
from .subscriptions.api import router as subscriptions_router
from .webhooks.api import router as webhooks_router


class PDJNinjaAPI(NinjaAPI):
    def validation_error_from_error_contexts(
        self, error_contexts: list[ValidationErrorContext]
    ) -> ValidationError:
        errors: list[dict[str, Any]] = []
        for context in error_contexts:
            e = context.pydantic_validation_error
            for i in e.errors(include_url=False):
                # removing pydantic hints
                del i["input"]  # type: ignore
                if (
                    "ctx" in i
                    and "error" in i["ctx"]
                    and isinstance(i["ctx"]["error"], Exception)
                ):
                    i["ctx"]["error"] = str(i["ctx"]["error"])
                errors.append(dict(i))
        return ValidationError(errors)


api = PDJNinjaAPI(title=f"{settings.PDJ_TITLE_NAME} API", csrf=False)

api.add_router("/mailing/", mailing_router)
api.add_router("/users/", users_router)
api.add_router("/plans/", plans_router)
api.add_router("/subscriptions/", subscriptions_router)
api.add_router("/webhooks/", webhooks_router)

reg_oidc_exceptions(api)
