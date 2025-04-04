import threading
import logging


_local_storage = threading.local()
logger = logging.getLogger(__name__)


class CurrentRequestMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _local_storage.request = request
        response = self.get_response(request)
        return response


def get_current_request():
    return getattr(_local_storage, "request", None)
