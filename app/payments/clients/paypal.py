from typing import Any, TypedDict
import logging
from decimal import Decimal
from django.utils import timezone
import requests
from requests.auth import HTTPBasicAuth
from requests import Response


from .base import PaymentClient


logger = logging.getLogger(__name__)


class PaypalWebhookHeaders(TypedDict):
    auth_algo: str
    cert_url: str
    transmission_id: str
    transmission_sig: str
    transmission_time: str


class OriginalPayPalClient:

    def __init__(self, client_id: str, client_secret: str, is_sandbox: bool):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = (
            "https://api.sandbox.paypal.com"
            if is_sandbox
            else "https://api-m.paypal.com"
        )
        # TODO: Refetch on expire
        self.access_token = self._get_access_token()
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def _make_request(
        self, url: str, method: str, raise_on_code=True, **kwargs
    ) -> Response:
        response = requests.request(method, url, **kwargs)
        if raise_on_code:
            try:
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                logger.error(f"PayPal request failed: {e.response.text}")
                raise e
        return response

    def _get_access_token(self) -> str:
        url = f"{self.base_url}/v1/oauth2/token"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {"grant_type": "client_credentials"}

        response = requests.post(
            url,
            headers=headers,
            data=data,
            auth=HTTPBasicAuth(self.client_id, self.client_secret),
        )
        response.raise_for_status()
        return response.json()["access_token"]

    def create_billing_subscription(
        self,
        plan_id: str,
        custom_id: str,
        *,
        return_url: str | None = None,
        cancel_url: str | None = None,
        start_time: str | None = None,
    ) -> dict[str, Any]:

        data = {
            "plan_id": plan_id,
            "custom_id": custom_id,
            "application_context": {"return_url": return_url, "cancel_url": cancel_url},
            "start_time":  None if start_time is None else start_time,
        }

        url = f"{self.base_url}/v1/billing/subscriptions"
        return self._make_request(
            url=url, method="POST", json=data, headers=self.headers
        ).json()

    def cancel_billing_subscription(self, subscription_id: str, reason: str) -> None:
        data = {
            "reason": reason,
        }

        url = f"{self.base_url}/v1/billing/subscriptions/{subscription_id}/cancel"
        self._make_request(url=url, method="POST", json=data, headers=self.headers)

    def suspend_billing_subscription(self, subscription_id: str, reason: str) -> None:
        data = {
            "reason": reason,
        }

        url = f"{self.base_url}/v1/billing/subscriptions/{subscription_id}/suspend"
        self._make_request(url=url, method="POST", json=data, headers=self.headers)

    def activate_billing_subscription(self, subscription_id: str, reason: str) -> None:
        data = {
            "reason": reason,
        }

        url = f"{self.base_url}/v1/billing/subscriptions/{subscription_id}/activate"
        self._make_request(url=url, method="POST", json=data, headers=self.headers)

    def show_subscription_details(self, subscription_id: str):
        data = {}
        url = f"{self.base_url}/v1/billing/subscriptions/{subscription_id}"
        # print(url)
        return self._make_request(
            url=url, method="GET", json=data, headers=self.headers
        ).json()
    def list_transactions_for_subscription_orig(self, subscription_id: str):
        data = {}
        url = f"{self.base_url}/v1/billing/subscriptions/{subscription_id}/transactions?start_time=2020-01-21T07:50:20.940Z&end_time=2050-08-21T07:50:20.940Z"
        return self._make_request(
            url=url, method="GET", json=data, headers=self.headers
        ).json()

    def list_webhooks_orig(self):
        data = {}
        url = f"{self.base_url}/v1/notifications/webhooks"
        return self._make_request(
            url=url, method="GET", json=data, headers=self.headers
        ).json()

    def revise_billing_subscription(
        self,
        subscription_id: str,
        plan_id: str,
        *,
        return_url: str | None = None,
        cancel_url: str | None = None,
    ) -> dict[str, Any]:
        data = {
            "plan_id": plan_id,
            "application_context": {"return_url": return_url, "cancel_url": cancel_url},
        }

        url = f"{self.base_url}/v1/billing/subscriptions/{subscription_id}/revise"
        return self._make_request(
            url=url,
            method="POST",
            json=data,
            headers=self.headers,
        ).json()

    def create_subscription_plan(
        self,
        product_id: str,
        name: str,
        description: str,
        interval_unit: str,
        interval_count: int,
        price: str,
        currency: str = "USD",
    ) -> dict[str, Any]:
        data = {
            "product_id": product_id,
            "name": name,
            "description": description,
            "status": "ACTIVE",
            "billing_cycles": [
                {
                    "frequency": {
                        "interval_unit": interval_unit,
                        "interval_count": interval_count,
                    },
                    "tenure_type": "REGULAR",
                    "sequence": 1,
                    "total_cycles": 0,
                    "pricing_scheme": {
                        "fixed_price": {"value": price, "currency_code": currency}
                    },
                }
            ],
            "payment_preferences": {
                "auto_bill_outstanding": True,
                "setup_fee_failure_action": "CONTINUE",
                "payment_failure_threshold": 3,
            },
        }
        url = f"{self.base_url}/v1/billing/plans"
        return self._make_request(
            url=url, method="POST", json=data, headers=self.headers
        ).json()

    def update_subscription_plan(self, id: str, name: str, description: str) -> None:
        data = [
            {
                "op": "replace",
                "path": "/name",
                "value": name,
            },
            {
                "op": "replace",
                "path": "/description",
                "value": description,
            },
        ]
        url = f"{self.base_url}/v1/billing/plans/{id}"
        return self._make_request(
            url=url, method="PATCH", json=data, headers=self.headers
        )

    def update_pricing_plan(
        self,
        id: str,
        price: str,
        currency: str = "USD",
    ) -> None:
        data = {
            "pricing_schemes": [
                {
                    "billing_cycle_sequence": 1,
                    "pricing_scheme": {
                        "fixed_price": {"value": price, "currency_code": currency}
                    },
                }
            ]
        }
        url = f"{self.base_url}/v1/billing/plans/{id}/update-pricing-schemes"
        return self._make_request(
            url=url, method="POST", json=data, headers=self.headers
        )

    def list_subscription_plan(
        self, product_id: str, page_size=10, page=1, total_required=False
    ) -> dict[str, Any]:
        params = {
            "product_id": product_id,
            "page_size": page_size,
            "page": page,
            "total_required": total_required,
        }
        url = f"{self.base_url}/v1/billing/plans"
        return self._make_request(
            url=url, method="GET", params=params, headers=self.headers
        ).json()

    def activate_subscription_plan(self, plan_id: str) -> None:
        data = {}

        url = f"{self.base_url}/v1/billing/plans/{plan_id}/activate"
        self._make_request(url=url, method="POST", json=data, headers=self.headers)

    def deactivate_subscription_plan(self, plan_id: str) -> None:
        data = {}

        url = f"{self.base_url}/v1/billing/plans/{plan_id}/deactivate"
        self._make_request(url=url, method="POST", json=data, headers=self.headers)

    def list_products(
        self, page_size=10, page=1, total_required=False
    ) -> dict[str, Any]:
        params = {
            "page_size": page_size,
            "page": page,
            "total_required": total_required,
        }
        url = f"{self.base_url}/v1/catalogs/products"
        return self._make_request(
            url=url, method="GET", params=params, headers=self.headers
        ).json()

    def create_product(
        self,
        id: str,
        name: str,
    ) -> dict[str, Any]:
        data = {
            "id": id,
            "name": name,
            "type": "DIGITAL",
        }

        url = f"{self.base_url}/v1/catalogs/products"
        return self._make_request(
            url=url, method="POST", json=data, headers=self.headers
        ).json()

    def verify_webhook_signature(
        self,
        headers: PaypalWebhookHeaders,
        webhook_id: str,
        webhook_event: dict[str, Any],
    ) -> dict[str, str]:
        data = {
            "webhook_id": webhook_id,
            "webhook_event": webhook_event,
        }
        data.update(**headers)

        url = f"{self.base_url}/v1/notifications/verify-webhook-signature"
        return self._make_request(
            url=url, method="POST", json=data, headers=self.headers
        ).json()

    def create_order(
        self,
        custom_id: str,
        amount: str,
        currency: str = "USD",
        *,
        return_url: str | None = None,
        cancel_url: str | None = None,
    ) -> dict[str, Any]:
        data = {
            "intent": "CAPTURE",
            "payment_source": {
                "paypal": {
                    "experience_context": {
                        "payment_method_preference": "IMMEDIATE_PAYMENT_REQUIRED",
                        "landing_page": "LOGIN",
                        "shipping_preference": "GET_FROM_FILE",
                        "user_action": "PAY_NOW",
                        "return_url": return_url,
                        "cancel_url": cancel_url,
                    }
                }
            },
            "purchase_units": [
                {
                    "custom_id": custom_id,
                    "amount": {
                        "currency_code": currency,
                        "value": amount,
                    },
                },
            ],
        }

        url = f"{self.base_url}/v2/checkout/orders"
        return self._make_request(
            url=url, method="POST", json=data, headers=self.headers
        ).json()

    def capture_payment_for_order(self, id: str) -> None:
        data = {}

        url = f"{self.base_url}/v2/checkout/orders/{id}/capture"
        self._make_request(url=url, method="POST", json=data, headers=self.headers)

    def refund_payment_for_capture(self, id: str) -> None:
        data = {}

        url = f"{self.base_url}/v2/payments/captures/{id}/refund"
        self._make_request(url=url, method="POST", json=data, headers=self.headers)


class PayPalClient(PaymentClient, OriginalPayPalClient):

    @staticmethod
    def get_hateoas_url(links: list[dict[str, str]], rel="approve"):
        return next((link["href"] for link in links if link["rel"] == rel), None)

    def generate_checkout_data(
        self,
        custom_id: str,
        amount: Decimal,
        return_url: str | None = None,
        cancel_url: str | None = None,
    ) -> dict[str, str] | None:
        try:
            resp = self.create_order(
                custom_id, f"{amount:.2f}", return_url=return_url, cancel_url=cancel_url
            )
        except requests.exceptions.HTTPError as e:
            logger.error(e.response.text)
            return None

        data = {}
        logger.info(f"generate_checkout_data resp: {resp}")
        data["id"] = resp["id"]
        data["url"] = self.get_hateoas_url(resp.get("links", []), rel="payer-action")
        return data

    def generate_subscription_data(
        self,
        custom_id: str,
        plan_id: str,
        return_url: str | None = None,
        cancel_url: str | None = None,
        start_time: str | None = None,
    ) -> dict[str, str] | None:
        try:
            resp = self.create_billing_subscription(
                plan_id, custom_id, return_url=return_url, cancel_url=cancel_url, start_time=start_time
            )
        except requests.exceptions.HTTPError as e:
            logger.error(e.response.text)
            return None

        data = {}
        logger.info(f"generate_subscription_data resp: {resp}")
        data["id"] = resp["id"]
        data["url"] = self.get_hateoas_url(resp.get("links", []))
        return data

    def activate_subscription(self, id: str, reason: str):
        try:
            self.activate_billing_subscription(id, reason)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 422:
                logger.warning(
                    f"Failed to proceed subscription cancel, details: {e.response.text}"
                )
                return
            raise e

    def deactivate_subscription(self, id: str, reason: str, suspend: bool = True):
        try:
            if suspend:
                self.suspend_billing_subscription(id, reason)
            else:
                self.cancel_billing_subscription(id, reason)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 422:
                logger.warning(
                    f"Failed to proceed subscription cancel, details: {e.response.text}"
                )
                return
            raise e

    def get_subscription_details(self, id: str):
        try:
            rsp = self.show_subscription_details(id)
            # print(rsp)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 422:
                logger.warning(
                    f"Failed to proceed subscription cancel, details: {e.response.text}"
                )
                return
            raise e
        return rsp

    def list_transactions_for_subscription(self, id: str):
        try:
            rsp = self.list_transactions_for_subscription_orig(id)
            # print(rsp)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 422:
                logger.warning(
                    f"Failed to proceed subscription cancel, details: {e.response.text}"
                )
                return
            raise e
        return rsp
        
    def list_webhooks(self):
        try:
            rsp = self.list_webhooks_orig()
            # print(rsp)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 422:
                logger.warning(
                    f"Failed to proceed subscription cancel, details: {e.response.text}"
                )
                return
            raise e
        return rsp

    def generate_change_subscription_data(
        self,
        id: str,
        to_plan_id: str,
        return_url: str | None = None,
        cancel_url: str | None = None,
    ) -> dict[str, str] | None:
        try:
            resp = self.revise_billing_subscription(
                id, to_plan_id, return_url=return_url, cancel_url=cancel_url
            )
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 422:
                logger.warning(
                    f"Failed to proceed subscription change, details: {e.response.text}"
                )
                return
            raise e

        data = {}
        logger.info(f"generate_change_subscription_data resp: {resp}")
        data["url"] = self.get_hateoas_url(resp.get("links", []))
        return data

    def approve_order(self, id: str):
        self.capture_payment_for_order(id)

    def refund_payment(self, id: str):
        self.refund_payment_for_capture(id)
