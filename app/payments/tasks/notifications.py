from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext as _
from django.db import transaction
from django.db.models import Q

from requests.exceptions import RequestException
from celery import shared_task
from celery.utils.log import get_task_logger

from ..models import Plan, Processor, PlanProcessorLink


logger = get_task_logger(__name__)


# @shared_task()
def notify_for_renew():
    pass
