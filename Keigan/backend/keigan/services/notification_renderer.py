"""Renders notification emails (HTML + text) and Teams Adaptive Cards from templates and the EN/JA string tables.

Autoescape is ON for email HTML. Body text coming from AI or users is converted with ``markdown_to_safe_html`` (escape first, then format).
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from keigan.config.settings import RESOURCES_DIRECTORY, get_settings

TEMPLATES_DIRECTORY = RESOURCES_DIRECTORY / "templates"
SUPPORTED_LANGUAGE_CODES = ("en", "ja")
FALLBACK_LANGUAGE_CODE = "en"


@dataclass
class RenderedEmail:
    subject_line: str
    body_html: str
    body_text: str


@lru_cache(maxsize=4)
def _string_table(language_code: str) -> dict[str, Any]:
    table_path = RESOURCES_DIRECTORY / "i18n" / f"{language_code}.json"
    return json.loads(table_path.read_text(encoding="utf-8"))


def resolve_language_code(language_code: str | None) -> str:
    short_code = (language_code or FALLBACK_LANGUAGE_CODE).split("-")[0].lower()
    return short_code if short_code in SUPPORTED_LANGUAGE_CODES else FALLBACK_LANGUAGE_CODE


def translate(language_code: str | None, dotted_path: str, **format_values: Any) -> str:
    """Looks a string up in the requested language, falling back to English; ``{placeholders}`` are formatted."""
    for candidate_language in (resolve_language_code(language_code), FALLBACK_LANGUAGE_CODE):
        node: Any = _string_table(candidate_language)
        for path_part in dotted_path.split("."):
            node = node.get(path_part) if isinstance(node, dict) else None
        if isinstance(node, str):
            try:
                return node.format(**format_values)
            except (KeyError, IndexError):
                return node
    return dotted_path


def markdown_to_safe_html(markdown_text: str | None) -> str:
    """Tiny Markdown subset (headings, bullets, bold, inline code, paragraphs) on already-escaped text."""
    if not markdown_text:
        return ""
    output_parts: list[str] = []
    open_list = False
    for raw_line in markdown_text.splitlines():
        line = html.escape(raw_line.rstrip())
        line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
        line = re.sub(r"`(.+?)`", r"<code>\1</code>", line)
        bullet_match = re.match(r"^\s*[-*]\s+(.*)$", line)
        if bullet_match:
            if not open_list:
                output_parts.append('<ul style="margin:6px 0 6px 18px;padding:0;">')
                open_list = True
            output_parts.append(f"<li>{bullet_match.group(1)}</li>")
            continue
        if open_list:
            output_parts.append("</ul>")
            open_list = False
        heading_match = re.match(r"^(#{1,4})\s+(.*)$", line)
        if heading_match:
            output_parts.append(f'<h3 style="margin:14px 0 4px 0;font-size:15px;color:#0061a0;">{heading_match.group(2)}</h3>')
        elif line.strip():
            output_parts.append(f'<p style="margin:6px 0;">{line}</p>')
    if open_list:
        output_parts.append("</ul>")
    return "\n".join(output_parts)


class NotificationRenderer:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._email_environment = Environment(loader=FileSystemLoader(TEMPLATES_DIRECTORY / "email"), autoescape=select_autoescape(["html", "j2"], default=True), trim_blocks=True, lstrip_blocks=True)
        self._text_environment = Environment(loader=FileSystemLoader(TEMPLATES_DIRECTORY / "email"), autoescape=False, trim_blocks=True, lstrip_blocks=True)
        self._card_environment = Environment(loader=FileSystemLoader(TEMPLATES_DIRECTORY / "teams"), autoescape=False)

    def render_email(
        self,
        notification_type: str,
        language_code: str | None,
        application_name: str,
        title: str,
        *,
        facts: list[tuple[str, str]] | None = None,
        body_markdown: str | None = None,
        action_path: str | None = None,
        subject_override: str | None = None,
        severity: str = "",
        priority: str = "",
    ) -> RenderedEmail:
        language = resolve_language_code(language_code)
        format_values = {"application_name": application_name, "title": title, "severity": severity, "priority": priority}
        subject_line = subject_override or translate(language, f"types.{notification_type}.subject", **format_values)
        context = {
            "language_code": language,
            "subject_line": subject_line,
            "layout": _string_table(language)["layout"] if language in SUPPORTED_LANGUAGE_CODES else _string_table(FALLBACK_LANGUAGE_CODE)["layout"],
            "headline": translate(language, f"types.{notification_type}.headline"),
            "intro": translate(language, f"types.{notification_type}.intro", **format_values),
            "facts": [{"label": label, "value": value} for label, value in (facts or []) if value],
            "body_html": markdown_to_safe_html(body_markdown),
            "body_text": body_markdown or "",
            "action_url": f"{self.settings.frontend_base_url.rstrip('/')}{action_path}" if action_path else None,
            "footer": translate(language, "layout.footer", application_name=application_name),
        }
        return RenderedEmail(
            subject_line=subject_line,
            body_html=self._email_environment.get_template("notification.html.j2").render(**context),
            body_text=self._text_environment.get_template("notification.txt.j2").render(**context),
        )

    def render_card(
        self, card_name: str, language_code: str | None, heading_key: str, title: str, summary: str, facts: list[tuple[str, str]], action_path: str | None = None
    ) -> dict[str, Any]:
        language = resolve_language_code(language_code)
        rendered = self._card_environment.get_template(f"{card_name}.json.j2").render(
            heading=translate(language, f"cards.{heading_key}"), title=title, summary=summary, facts=[{"label": label, "value": value} for label, value in facts if value],
            open_label=translate(language, "cards.open"), action_url=f"{self.settings.frontend_base_url.rstrip('/')}{action_path}" if action_path else None,
        )
        return json.loads(rendered)
