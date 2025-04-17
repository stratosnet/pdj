class PaymentException(BaseException):
    pass


class PaymentNotFound(PaymentException):
    pass


class PaymentWrongStatus(PaymentException):
    pass


class SubscriptionNotFound(PaymentException):
    pass


class PlanNotFound(PaymentException):
    pass
