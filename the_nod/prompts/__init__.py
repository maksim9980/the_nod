"""Driver prompt texts: plain Markdown files `<adapter>/<lang>/<kind>.md` next to this module."""
from pathlib import Path

from the_nod import i18n

_DIR = Path(__file__).parent
TEMPLATE = "brief-template"
TEMPLATE_ADAPTER = "default"


def load(adapter: str, kind: str, lang: str) -> str:
    """Prompt `kind` of `adapter` in `lang`; an unknown language raises `i18n.LangError`."""
    if lang not in i18n.LANGS:
        raise i18n.LangError(f"lang={lang}: unknown language, use {' or '.join(i18n.LANGS)}")
    return (_DIR / adapter / lang / f"{kind}.md").read_text(encoding="utf-8")


def template(lang: str) -> str:
    """The brief template in `lang`: the same block the brief prompt carries."""
    return load(TEMPLATE_ADAPTER, TEMPLATE, lang)
