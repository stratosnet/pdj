from decimal import Decimal
from abc import ABC, abstractmethod


class PaymentClient(ABC):
    @abstractmethod
    def generate_subscription_data(
        self,
        plan_id: str,
        custom_id: str,
        return_url: str | None = None,
        cancel_url: str | None = None,
    ) -> dict[str, str] | None:
        pass

    @abstractmethod
    def activate_subscription(self, id: str, reason: str):
        pass

    @abstractmethod
    def deactivate_subscription(self, id: str, reason: str, suspend: bool = True):
        pass

    @abstractmethod
    def generate_change_subscription_data(
        self,
        id: str,
        to_plan_id: str,
        return_url: str | None = None,
        cancel_url: str | None = None,
    ) -> dict[str, str] | None:
        pass
