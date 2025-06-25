from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext as _
from django.db import transaction
from django.db.models import Q

from celery import shared_task
from celery.utils.log import get_task_logger

from ..models import PaymentUrlCache


logger = get_task_logger(__name__)


@shared_task
def payment_url_cache():
    now = timezone.now()
    threshold = now + timezone.timedelta(minutes=1)
    deleted_count, _ = PaymentUrlCache.objects.filter(expired_at__lt=threshold).delete()

    if deleted_count > 0:
        logger.info(
            f"Purged {deleted_count} payment URL cache entries with expired time (including those expiring within 1 minute)."
        )
        return
    logger.info("No expired payment URL cache entries to purge.")
