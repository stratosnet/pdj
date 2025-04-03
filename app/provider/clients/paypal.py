from typing import Any
import requests
from requests.auth import HTTPBasicAuth
from requests import Response


class PayPalClient:

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

    def _make_request(self, url: str, method: str, **kwargs) -> Response:
        response = requests.request(method, url, **kwargs)
        response.raise_for_status()
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

    def create_subscription(
        self, plan_id: str, custom_id: str, return_url: str, cancel_url: str
    ) -> dict[str, Any]:
        data = {
            "plan_id": plan_id,
            "custom_id": custom_id,
            "application_context": {"return_url": return_url, "cancel_url": cancel_url},
        }

        url = f"{self.base_url}/v1/billing/subscriptions"
        return self._make_request(
            url=url, method="POST", json=data, headers=self.headers
        ).json()

    def cancel_subscription(self, subscription_id: str, reason: str) -> None:
        data = {
            "reason": reason,
        }

        url = f"{self.base_url}/v1/billing/subscriptions/{subscription_id}/cancel"
        self._make_request(url=url, method="POST", json=data, headers=self.headers)

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
            "billing_cycles": [
                {
                    "tenure_type": "REGULAR",
                    "frequency": {
                        "interval_unit": interval_unit,
                        "interval_count": interval_count,
                    },
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
