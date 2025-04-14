import os
import random
import string
import secrets
import binascii


def mask_secret(text: str, keep_first=4):
    if len(text) > keep_first:
        text = text[:4] + "*" * (len(text) - keep_first)
    return text


def generate_sku_prefix(length=4):
    characters = string.ascii_uppercase
    return "".join(random.choice(characters) for _ in range(length))


def generate_base_secret(length=20):
    return binascii.hexlify(os.urandom(length)).decode()
