import logging

from django.http import HttpRequest
from ninja.security.base import AuthBase

from ._base import api
from .authenticators.fief import oidc_auth
from .authenticators.client import client_auth
from .schemas import Checkout

from core.models import Client, SSOUser
from payment.models import Plan
from provider.models import PaymentReference, Processor


logger = logging.getLogger(__name__)


def multi_auth(authenticators: list[AuthBase]):
    def wrapper(request):
        is_auth = None
        for auth in authenticators:
            is_auth = auth(request)
            if is_auth is None:
                return
        return is_auth

    return wrapper


@api.post("/payments/checkout", auth=multi_auth([client_auth, oidc_auth]))
def checkout(request: HttpRequest, data: Checkout):
    print("request", request)
    print("request.sso", request.sso)
    print("request.client", request.client)
    plan = Plan.objects.get(id=data.plan_id, is_enabled=True)

    # pr = PaymentReference.objects.select_related("processor").get(
    #     processor=data.payment_method_id, object_id=plan.id
    # )
    # provider = pr.processor.get_provider()

    print("plan", plan)
    return {"": ""}
