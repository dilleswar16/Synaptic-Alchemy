"""The one sanitiser for every piece of AI-written markdown or text that Keigan stores or sends (V8).

The text is parsed as CommonMark (markdown-it-py) and written back out from the parse tree, so only what the parser really sees
as a link or image is changed, whatever trick was used to write it (titles, upper-case schemes, autolinks, reference links,
protocol-relative URLs, ``\\@`` host tricks, bare URLs). Rules:

- A link is kept only when its host is on the allow-list (exact host match, or ``*.suffix`` entries) and it has no user-info.
  Any other link becomes its text plus the host in code formatting; a bare or autolinked URL becomes inline code.
- Images become their alt text. Raw HTML is escaped. Link titles are dropped.
- Invisible characters (format, private-use, unassigned, tag block) are removed.
- Text that could form a link or a reference definition after the round trip is escaped; citation codes like ``[E3]`` are not.

Call it before storing AI text and again before sending it (email, Teams), so outgoing content is always sanitised.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from urllib.parse import urlsplit

from markdown_it import MarkdownIt
from markdown_it.token import Token

from keigan.ai.ai_safety_settings import get_ai_safety_settings
from keigan.ai.prompt_safety import strip_invisible_characters

_PARSER = MarkdownIt("commonmark", {"html": True}).enable(["table", "strikethrough"])
_BARE_URL_PATTERN = re.compile(r"(?i)(?<![\w/@])(?:https?://|www\.)[^\s<>`]+")
_TRAILING_URL_PUNCTUATION = ".,;:!?)]}'\""
_ASCII_PUNCTUATION = frozenset("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")
_BRACKET_FOLLOWERS = frozenset("([:")
_HTML_ENTITY_PATTERN = re.compile(r"&(?:#\d+|#[xX][0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);")
_LINE_START_MARKER_PATTERN = re.compile(r"^(?P<lead>\s{0,3})(?P<marker>#{1,6}(?=\s|$)|[-+*](?=\s|$)|>|\d{1,9}[.)](?=\s|$)|={2,}$|-{2,}$|(?:\*\s*){3,}$)")
_CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_BROWSER_IGNORED_URL_CHARACTERS = re.compile(r"[\t\r\n\x00-\x20]")
_ENCODED_BACKSLASH_PATTERN = re.compile(r"%5c", re.IGNORECASE)


def is_allowed_link(url: str, allowed_hosts: Iterable[str]) -> bool:
    """True only for http(s) URLs without user-info whose host is on the allow-list. Mirrors how a browser reads the URL."""
    return _allowed_host_of(url, allowed_hosts) is not None


def _read_url(url: str) -> tuple[str | None, bool]:
    """(host, has_user_info) as a browser would read ``url``; the host is None without an http(s) scheme or host."""
    browser_url = _BROWSER_IGNORED_URL_CHARACTERS.sub("", unicodedata.normalize("NFKC", url.strip()))
    browser_url = _ENCODED_BACKSLASH_PATTERN.sub("/", browser_url).replace("\\", "/")  # browsers treat a backslash as a slash
    if browser_url.lower().startswith("www."):
        browser_url = "https://" + browser_url
    try:
        parts = urlsplit(browser_url)
        host = (parts.hostname or "").rstrip(".").lower()
    except ValueError:
        return None, False
    if parts.scheme.lower() not in ("http", "https") or not host:
        return None, False
    return host, "@" in parts.netloc


def _allowed_host_of(url: str, allowed_hosts: Iterable[str]) -> str | None:
    host, has_user_info = _read_url(url)
    if host is None or has_user_info:
        return None
    for allowed_host in allowed_hosts:
        if allowed_host.startswith("*."):
            if host.endswith(allowed_host[1:]) and len(host) > len(allowed_host) - 1:
                return host
        elif host == allowed_host:
            return host
    return None


class _Serializer:
    """Writes a markdown-it token stream back to markdown, applying the link and image rules."""

    def __init__(self, allowed_hosts: frozenset[str]):
        self.allowed_hosts = allowed_hosts

    # ── Blocks ─────────────────────────────────────────────────────────────────
    def render_blocks(self, tokens: list[Token]) -> str:
        blocks: list[str] = []
        token_index = 0
        while token_index < len(tokens):
            block_text, token_index = self._render_block(tokens, token_index)
            if block_text is not None:
                blocks.append(block_text)
        return "\n\n".join(blocks)

    def _closing_index(self, tokens: list[Token], opening_index: int) -> int:
        depth = 0
        for token_index in range(opening_index, len(tokens)):
            depth += tokens[token_index].nesting
            if depth == 0:
                return token_index
        return len(tokens) - 1

    def _render_block(self, tokens: list[Token], token_index: int) -> tuple[str | None, int]:
        token = tokens[token_index]
        if token.nesting == 0:
            return self._render_leaf_block(token), token_index + 1
        closing_index = self._closing_index(tokens, token_index)
        inner_tokens = tokens[token_index + 1 : closing_index]
        if token.type == "paragraph_open":
            rendered = self._render_inline(inner_tokens[0])
        elif token.type == "heading_open":
            rendered = f"{'#' * int(token.tag[1:])} {self._render_inline(inner_tokens[0])}"
        elif token.type == "blockquote_open":
            rendered = "\n".join(f"> {line}".rstrip() for line in self.render_blocks(inner_tokens).split("\n"))
        elif token.type in ("bullet_list_open", "ordered_list_open"):
            rendered = self._render_list(token, inner_tokens)
        elif token.type == "table_open":
            rendered = self._render_table(inner_tokens)
        else:
            rendered = self.render_blocks(inner_tokens)
        return rendered, closing_index + 1

    def _render_leaf_block(self, token: Token) -> str | None:
        if token.type == "fence":
            fence_markup = token.markup or "```"
            return f"{fence_markup}{token.info}\n{token.content}{fence_markup}"
        if token.type == "code_block":
            return "\n".join(f"    {line}" if line else "" for line in token.content.rstrip("\n").split("\n"))
        if token.type == "hr":
            return "---"
        if token.type == "html_block":
            return "\n".join(self._escape_html_line(line) for line in token.content.rstrip("\n").split("\n"))
        if token.type == "inline":
            return self._render_inline(token)
        return None

    @staticmethod
    def _escape_html_line(line: str) -> str:
        return line.replace("<", "\\<")

    def _render_list(self, list_token: Token, item_tokens: list[Token]) -> str:
        rendered_items: list[str] = []
        is_ordered = list_token.type == "ordered_list_open"
        token_index = 0
        while token_index < len(item_tokens):
            item_open = item_tokens[token_index]
            closing_index = self._closing_index(item_tokens, token_index)
            item_inner = item_tokens[token_index + 1 : closing_index]
            is_tight = all(inner.hidden for inner in item_inner if inner.type == "paragraph_open")
            separator = "\n" if is_tight else "\n\n"
            item_blocks: list[str] = []
            inner_index = 0
            while inner_index < len(item_inner):
                block_text, inner_index = self._render_block(item_inner, inner_index)
                if block_text is not None:
                    item_blocks.append(block_text)
            marker = f"{item_open.info}{item_open.markup}" if is_ordered else (item_open.markup or "-")
            indent = " " * (len(marker) + 1)
            body_lines = separator.join(item_blocks).split("\n")
            rendered_items.append(f"{marker} {body_lines[0]}".rstrip() + "".join("\n" + (indent + line if line else "") for line in body_lines[1:]))
            token_index = closing_index + 1
        return "\n".join(rendered_items) if all("\n\n" not in item for item in rendered_items) else "\n\n".join(rendered_items)

    def _render_table(self, table_tokens: list[Token]) -> str:
        rows: list[list[str]] = []
        alignments: list[str] = []
        for token_index, token in enumerate(table_tokens):
            if token.type == "tr_open":
                rows.append([])
            elif token.type in ("th_open", "td_open"):
                cell_text = self._render_inline(table_tokens[token_index + 1]).replace("|", "\\|").replace("\n", " ")
                rows[-1].append(cell_text)
                if token.type == "th_open":
                    style = token.attrGet("style") or ""
                    alignments.append(":---:" if "center" in str(style) else "---:" if "right" in str(style) else ":---" if "left" in str(style) else "---")
        lines = ["| " + " | ".join(row) + " |" for row in rows]
        lines.insert(1, "| " + " | ".join(alignments) + " |")
        return "\n".join(lines)

    # ── Inline ─────────────────────────────────────────────────────────────────
    def _render_inline(self, inline_token: Token) -> str:
        return self._render_children(inline_token.children or [])

    def _render_children(self, children: list[Token]) -> str:
        pieces: list[str] = []
        at_line_start = True
        child_index = 0
        while child_index < len(children):
            child = children[child_index]
            if child.type == "text":
                pieces.append(self._escape_text(child.content, at_line_start))
                at_line_start = False
            elif child.type in ("softbreak", "hardbreak"):
                pieces.append("  \n" if child.type == "hardbreak" else "\n")
                at_line_start = True
            elif child.type == "code_inline":
                markup = child.markup or "`"
                padding = " " if child.content.startswith("`") or child.content.endswith("`") else ""
                pieces.append(f"{markup}{padding}{child.content}{padding}{markup}")
                at_line_start = False
            elif child.type in ("strong_open", "strong_close", "em_open", "em_close", "s_open", "s_close"):
                pieces.append(child.markup)
                at_line_start = False
            elif child.type == "html_inline":
                pieces.append(child.content.replace("<", "\\<"))
                at_line_start = False
            elif child.type == "image":
                pieces.append(self._plain_text_of(child.children or []))
                at_line_start = False
            elif child.type == "link_open":
                closing_index = self._closing_index(children, child_index)
                pieces.append(self._render_link(child, children[child_index + 1 : closing_index]))
                child_index = closing_index
                at_line_start = False
            child_index += 1
        return "".join(pieces)

    def _plain_text_of(self, children: list[Token]) -> str:
        return "".join(child.content for child in children if child.type in ("text", "code_inline"))

    def _render_link(self, link_open: Token, link_children: list[Token]) -> str:
        destination = str(link_open.attrGet("href") or "")
        allowed_host = _allowed_host_of(destination, self.allowed_hosts)
        is_autolink = link_open.markup == "autolink"
        if is_autolink:
            return f"<{destination}>" if allowed_host else f"`{destination}`"
        link_text = self._render_children(link_children)
        if allowed_host:
            safe_destination = destination.replace("(", "%28").replace(")", "%29").replace(" ", "%20")
            return f"[{link_text}]({safe_destination})"
        host, has_user_info = _read_url(destination)
        return f"{link_text} (`{host}`)" if host and not has_user_info else link_text  # a host with user-info would mislead

    # ── Text escaping ──────────────────────────────────────────────────────────
    def _escape_text(self, text: str, at_line_start: bool) -> str:
        """Escape what could turn into markup after the round trip; bare URLs of other hosts are shown as inline code."""
        pieces: list[str] = []
        position = 0
        for url_match in _BARE_URL_PATTERN.finditer(text):
            url = url_match.group(0).rstrip(_TRAILING_URL_PUNCTUATION)
            if not url or _allowed_host_of(url, self.allowed_hosts):
                continue
            pieces.append(self._escape_plain(text[position : url_match.start()], at_line_start and position == 0))
            pieces.append(f"`{url}`")
            position = url_match.start() + len(url)
        pieces.append(self._escape_plain(text[position:], at_line_start and position == 0))
        return "".join(pieces)

    @staticmethod
    def _escape_plain(text: str, at_line_start: bool) -> str:
        escaped: list[str] = []
        previous_character = ""
        for position, character in enumerate(text):
            next_character = text[position + 1] if position + 1 < len(text) else ""
            if character in "`*<" or (character == "~" and next_character == "~"):
                escaped.append("\\" + character)
            elif character == "\\" and next_character in _ASCII_PUNCTUATION:
                escaped.append("\\\\")
            elif character == "_" and not (previous_character.isalnum() and next_character.isalnum()):
                escaped.append("\\_")
            elif character == "&" and _HTML_ENTITY_PATTERN.match(text, position):
                escaped.append("\\&")
            elif previous_character == "]" and character in _BRACKET_FOLLOWERS:
                escaped.append("\\" + character)
            else:
                escaped.append(character)
            previous_character = character
        escaped_text = "".join(escaped)
        if at_line_start:
            escaped_text = _LINE_START_MARKER_PATTERN.sub(lambda match: match.group("lead") + "\\" + match.group("marker"), escaped_text, count=1)
        return escaped_text


def sanitize_ai_markdown(markdown_text: str | None, allowed_hosts: Iterable[str] | None = None) -> str:
    """Safe markdown for AI-written text: link allow-list, images dropped, HTML escaped, invisible characters removed."""
    if not markdown_text:
        return ""
    effective_hosts = frozenset(allowed_hosts if allowed_hosts is not None else get_ai_safety_settings().allowed_link_hosts)
    cleaned_text = strip_invisible_characters(str(markdown_text)).replace("\r\n", "\n").replace("\r", "\n")
    return _Serializer(effective_hosts).render_blocks(_PARSER.parse(cleaned_text)).strip("\n")


def sanitize_ai_line(text: str | None, allowed_hosts: Iterable[str] | None = None, maximum_characters: int = 400) -> str:
    """A single-line AI field (email subject, title): sanitised like markdown, on one line, cut to ``maximum_characters``.

    Line breaks are removed so the value can never inject an email header or a new paragraph.
    """
    if not text:
        return ""
    single_line = _CONTROL_CHARACTER_PATTERN.sub(" ", re.sub(r"\s*[\r\n\u2028\u2029]+\s*", " ", str(text)))
    return sanitize_ai_markdown(single_line, allowed_hosts).replace("\n", " ")[:maximum_characters]
