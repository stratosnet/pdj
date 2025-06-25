import os
import random
import string
import binascii
import base64
import hashlib
from typing import Any
from urllib.parse import urljoin

from django.conf import settings
from django.utils import timezone
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from django.http import HttpRequest

from pydantic import ValidationError as PydanticValidationError
from ninja import Schema, NinjaAPI
from ninja.errors import ValidationErrorContext
from ninja.params.models import BodyModel

from .middleware import get_current_request


def mask_secret(text: str, keep_first=4):
    if len(text) > keep_first:
        text = text[:4] + "*" * (len(text) - keep_first)
    return text


def generate_sku_prefix(length=4):
    characters = string.ascii_uppercase
    return "".join(random.choice(characters) for _ in range(length))


def generate_base_secret(length=20):
    return binascii.hexlify(os.urandom(length)).decode()


def build_full_path(path: str):
    if settings.PDJ_DOMAIN:
        return urljoin(settings.PDJ_DOMAIN, path)

    request = get_current_request()
    if request:
        return request.build_absolute_uri(path)


def get_default_context():
    domain = settings.PDJ_DOMAIN
    if not domain:
        request = get_current_request()
        if request:
            domain = request.build_absolute_uri()
    return {
        "now": timezone.now(),
        "domain": domain,
    }


def make_timestamp_token(value: str):
    return base64.b64encode(TimestampSigner().sign(value).encode()).decode()


def get_value_from_timestamp_token(token):
    try:
        token = base64.b64decode(token).decode()
    except (ValueError, base64.binascii.Error):
        return "", False

    try:
        value = TimestampSigner().unsign(token, max_age=60 * 60 * 24 * 2)
    except (BadSignature, SignatureExpired):
        return "", False
    return value, True


def validate_schema_with_context(
    api: "NinjaAPI", request: HttpRequest, schema: Schema, data: Any
) -> Schema:
    try:
        data = schema.model_validate(data, context={"request": request})
        return data
    except PydanticValidationError as exc:
        error_contexts = [
            ValidationErrorContext(pydantic_validation_error=exc, model=BodyModel())
        ]
        validation_error = api.validation_error_from_error_contexts(error_contexts)
        raise validation_error


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
