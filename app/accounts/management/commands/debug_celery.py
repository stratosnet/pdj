import shlex
import subprocess
import logging

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import autoreload

logger = logging.getLogger(__name__)


def restart_celery():
    cmd = "pkill -9 celery"
    subprocess.call(shlex.split(cmd))
    cmd = "celery -A core worker -l info -c 2 -E"
    subprocess.call(shlex.split(cmd))


class Command(BaseCommand):

    def handle(self, *args, **options):
        if settings.DEBUG is False:
            return

        logger.info("Starting celery worker with autoreload...")
        autoreload.run_with_reloader(restart_celery)
