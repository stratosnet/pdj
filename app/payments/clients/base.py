from decimal import Decimal
from abc import ABC, abstractmethod


class PaymentClient(ABC):
    @abstractmethod
    def generate_subscription_data(
        self, plan_id: str, order_id: str, return_url: str, cancel_url: str
    ) -> dict[str, str] | None:
        pass
