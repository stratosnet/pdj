from decimal import Decimal
from abc import ABC, abstractmethod


class PaymentClient(ABC):
    @abstractmethod
    def generate_subscription_link(
        self, plan_id: str, order_id: str, return_url: str, cancel_url: str
    ) -> str | None:
        pass
