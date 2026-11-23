"""Renders notification emails (HTML + text) and Teams Adaptive Cards from templates and the EN/JA string tables.

Autoescape is ON for email HTML. Body text coming from AI or users is converted with ``markdown_to_safe_html`` (escape first, then format).
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from keigan.ai.output_sanitizer import sanitize_ai_line, sanitize_ai_markdown
from keigan.config.settings import RESOURCES_DIRECTORY, get_settings
from keigan.utils.string_table import FALLBACK_LANGUAGE_CODE, SUPPORTED_LANGUAGE_CODES, resolve_language_code, string_table, translate

TEMPLATES_DIRECTORY = RESOURCES_DIRECTORY / "templates"


@dataclass
class RenderedEmail:
    subject_line: str
    body_html: str
    body_text: str


_BACKSLASH_ESCAPE_PATTERN = re.compile(r"\\([!-/:-@\[-`{-~])")
_ESCAPED_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")


def markdown_to_safe_html(markdown_text: str | None) -> str:
    """Tiny Markdown subset (headings, bullets, bold, inline code, links, paragraphs, fenced code blocks) on already-escaped text.

    The text is sanitised first (links only to allowed hosts, no images or HTML), so the only links that can appear are allowed ones.
    """
    if not markdown_text:
        return ""
    output_parts: list[str] = []
    open_list = False
    fenced_lines: list[str] | None = None  # the lines of the fenced code block being read (a suggested command): escaped, never formatted
    for raw_line in sanitize_ai_markdown(markdown_text).splitlines():
        if raw_line.strip().startswith("```"):
            if fenced_lines is None:
                if open_list:
                    output_parts.append("</ul>")
                    open_list = False
                fenced_lines = []
            else:
                output_parts.append(_code_block_html(fenced_lines))
                fenced_lines = None
            continue
        if fenced_lines is not None:
            fenced_lines.append(raw_line.rstrip())
            continue
        line = html.escape(raw_line.rstrip())
        line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
        line = re.sub(r"`(.+?)`", r"<code>\1</code>", line)
        line = _ESCAPED_LINK_PATTERN.sub(r'<a href="\2">\1</a>', line)
        line = _BACKSLASH_ESCAPE_PATTERN.sub(r"\1", line)
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
    if fenced_lines is not None:  # an unclosed fence: still show what was written, as code
        output_parts.append(_code_block_html(fenced_lines))
    if open_list:
        output_parts.append("</ul>")
    return "\n".join(output_parts)


def _code_block_html(lines: list[str]) -> str:
    code = html.escape("\n".join(lines))
    return f'<pre style="margin:8px 0;padding:10px 12px;background:#f3f5f7;border:1px solid #d5dbe0;border-radius:6px;overflow:auto;font-size:13px;"><code>{code}</code></pre>'


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
        subject_line = sanitize_ai_line(subject_override) if subject_override else " ".join(translate(language, f"types.{notification_type}.subject", **format_values).split())  # one line: no header injection
        body_markdown = sanitize_ai_markdown(body_markdown)  # the last gate before an email leaves: only sanitised text is ever sent (V8)
        context = {
            "language_code": language,
            "subject_line": subject_line,
            "layout": string_table(language)["layout"] if language in SUPPORTED_LANGUAGE_CODES else string_table(FALLBACK_LANGUAGE_CODE)["layout"],
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
        self, card_name: str, language_code: str | None, heading_key: str, title: str, summary: str, facts: list[tuple[str, str]], action_path: str | None = None, extra_actions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        language = resolve_language_code(language_code)
        rendered = self._card_environment.get_template(f"{card_name}.json.j2").render(
            heading=translate(language, f"cards.{heading_key}"), title=sanitize_ai_line(title), summary=sanitize_ai_markdown(summary), facts=[{"label": label, "value": value} for label, value in facts if value],
            open_label=translate(language, "cards.open"), action_url=f"{self.settings.frontend_base_url.rstrip('/')}{action_path}" if action_path else None,
        )
        card: dict[str, Any] = json.loads(rendered)
        if extra_actions:
            card.setdefault("actions", []).extend(extra_actions)  # buttons the bot answers (roadmap D2), after the link that opens Keigan
        return card
