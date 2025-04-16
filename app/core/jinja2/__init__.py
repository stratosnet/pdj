from typing import Mapping

from jinja2 import Environment, DictLoader, select_autoescape

from . import filters


def get_jinja2_env(templates: Mapping[str, str] | None = None):
    env = Environment(
        loader=DictLoader(templates) if templates else None,
        autoescape=select_autoescape(["html", "xml"]) if templates else False,
    )
    for filter_name in filters.__all__:
        env.filters[filter_name] = getattr(filters, filter_name)
    return env
