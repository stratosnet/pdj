from ninja import Schema


class Checkout(Schema):
    plan_id: int
    payment_method_id: int
