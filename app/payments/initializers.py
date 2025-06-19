from django.conf import settings

from .models import Processor


class ProcessorInitializer:
    def initialize(self, log_func):
        if not Processor.objects.first():
            if settings.PDJ_PAYPAL_CLIENT_ID and settings.PDJ_PAYPAL_CLIENT_SECRET:
                Processor.objects.create(
                    type=Processor.Type.PAYPAL,
                    client_id=settings.PDJ_PAYPAL_CLIENT_ID,
                    secret=settings.PDJ_PAYPAL_CLIENT_SECRET,
                    endpoint_secret=settings.PDJ_PAYPAL_ENDPOINT_SECRET,
                    is_sandbox=(
                        settings.PDJ_PAYPAL_IS_SANDBOX
                        if settings.PDJ_PAYPAL_IS_SANDBOX
                        else True
                    ),
                    is_enabled=True,
                )
                log_func("Default paypal processor initialized")
