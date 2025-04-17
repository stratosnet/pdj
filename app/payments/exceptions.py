class PaymentException(BaseException):
    pass


class InvoiceNotFound(PaymentException):
    pass


class PaymentNotFound(PaymentException):
    pass


class PaymentWrongStatus(PaymentException):
    pass


class SubscriptionNotFound(PaymentException):
    pass


class PlanNotFound(PaymentException):
    pass
