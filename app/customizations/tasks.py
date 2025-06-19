import json
import smtplib

from django.conf import settings
from django.utils.translation import gettext as _
from django.core.mail import send_mail, mail_admins

from celery import shared_task
from celery.utils.log import get_task_logger


logger = get_task_logger(__name__)


@shared_task(exceptions=(smtplib.SMTPException,), retry_backoff=True)
def notify_admins(subject: str, message: str):
    mail_admins(
        subject=_(f"[ADMIN] Notification from {settings.PDJ_TITLE_NAME}: ") + subject,
        message=message,
        fail_silently=False,
    )
    logger.info(f"Admins notified with subject: {subject}")


@shared_task()
def send_template(type_: int, to: str, context_str: str | None = None):
    from .models import EmailTemplate

    template = EmailTemplate.objects.get_by_type(type_)
    if not template:
        logger.warning(f"Template '{type_}' does not exists")
        return

    context = json.loads(context_str or "{}")

    subject = template.render_subject(context)
    content = template.render_content(context)

    send_mail(
        subject=subject,
        message="",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[to],
        html_message=content,
    )
