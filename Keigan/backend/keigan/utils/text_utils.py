"""Text helpers: tokenisation (Latin + CJK), BM25 lexical ranking, Markdown chunking and heading extraction."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

_LATIN_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9_.-]{1,40}")
_CJK_RUN_PATTERN = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯]+")
_MARKDOWN_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$", re.MULTILINE)

STOP_WORDS = frozenset(
    "a an and are as at be by for from has have in is it its of on or that the this to was were will with not no "
    "into than then there these those which who what when where how why can could should would may might also".split()
)


def tokenize_for_search(text: str | None) -> list[str]:
    """Lower-case Latin words (camelCase and snake_case split) plus character bigrams for Japanese/Chinese/Korean."""
    if not text:
        return []
    split_camel_case_text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    lowercase_text = split_camel_case_text.lower()
    tokens: list[str] = []
    for latin_token in _LATIN_TOKEN_PATTERN.findall(lowercase_text):
        stripped_token = latin_token.strip("._-")
        if len(stripped_token) > 1 and stripped_token not in STOP_WORDS:
            tokens.append(stripped_token)
            if "_" in stripped_token or "-" in stripped_token or "." in stripped_token:
                tokens.extend(part for part in re.split(r"[_.-]", stripped_token) if len(part) > 1 and part not in STOP_WORDS)
    for cjk_run in _CJK_RUN_PATTERN.findall(text):
        tokens.extend(cjk_run[index : index + 2] for index in range(max(1, len(cjk_run) - 1)))
    return tokens


def term_frequencies(text: str | None) -> dict[str, int]:
    return dict(Counter(tokenize_for_search(text)))


@dataclass(frozen=True)
class RankedDocument:
    document_key: str
    score: float


def rank_with_bm25(
    query_text: str,
    documents_term_frequencies: dict[str, dict[str, int]],
    *,
    maximum_results: int = 10,
    term_saturation: float = 1.4,
    length_normalization: float = 0.75,
) -> list[RankedDocument]:
    """Okapi BM25 over pre-computed term frequencies (stored per chunk in ``search_terms_json``)."""
    query_terms = set(tokenize_for_search(query_text))
    if not query_terms or not documents_term_frequencies:
        return []
    document_count = len(documents_term_frequencies)
    document_lengths = {key: sum(frequencies.values()) or 1 for key, frequencies in documents_term_frequencies.items()}
    average_document_length = sum(document_lengths.values()) / document_count
    documents_containing_term = {
        query_term: sum(1 for frequencies in documents_term_frequencies.values() if query_term in frequencies) for query_term in query_terms
    }
    ranked_documents: list[RankedDocument] = []
    for document_key, frequencies in documents_term_frequencies.items():
        document_score = 0.0
        for query_term in query_terms:
            term_frequency = frequencies.get(query_term, 0)
            if not term_frequency:
                continue
            inverse_document_frequency = math.log(1 + (document_count - documents_containing_term[query_term] + 0.5) / (documents_containing_term[query_term] + 0.5))
            normalized_frequency = (term_frequency * (term_saturation + 1)) / (
                term_frequency + term_saturation * (1 - length_normalization + length_normalization * document_lengths[document_key] / average_document_length)
            )
            document_score += inverse_document_frequency * normalized_frequency
        if document_score > 0:
            ranked_documents.append(RankedDocument(document_key, round(document_score, 4)))
    return sorted(ranked_documents, key=lambda ranked_document: -ranked_document.score)[:maximum_results]


def extract_markdown_headings(markdown_text: str | None, maximum_headings: int = 60) -> list[str]:
    return [match.group(2).strip() for match in _MARKDOWN_HEADING_PATTERN.finditer(markdown_text or "")][:maximum_headings]


@dataclass(frozen=True)
class TextChunk:
    section_heading: str | None
    chunk_text: str


def chunk_markdown(markdown_text: str, target_characters: int = 2000, overlap_characters: int = 200) -> list[TextChunk]:
    """Heading-aware chunking (~500 tokens per chunk) that keeps each chunk's nearest heading for citations."""
    if not markdown_text.strip():
        return []
    sections: list[tuple[str | None, str]] = []
    current_heading: str | None = None
    current_lines: list[str] = []
    for line in markdown_text.splitlines():
        heading_match = _MARKDOWN_HEADING_PATTERN.match(line)
        if heading_match and current_lines:
            sections.append((current_heading, "\n".join(current_lines).strip()))
            current_lines = []
        if heading_match:
            current_heading = heading_match.group(2).strip()
        current_lines.append(line)
    if current_lines:
        sections.append((current_heading, "\n".join(current_lines).strip()))

    chunks: list[TextChunk] = []
    for section_heading, section_text in sections:
        if not section_text:
            continue
        start_index = 0
        while start_index < len(section_text):
            end_index = min(len(section_text), start_index + target_characters)
            if end_index < len(section_text):
                paragraph_break = section_text.rfind("\n\n", start_index + target_characters // 2, end_index)
                if paragraph_break > 0:
                    end_index = paragraph_break
            chunks.append(TextChunk(section_heading, section_text[start_index:end_index].strip()))
            if end_index >= len(section_text):
                break
            start_index = max(end_index - overlap_characters, start_index + 1)
    return [chunk for chunk in chunks if chunk.chunk_text]


def truncate_text(text: str | None, maximum_characters: int, suffix: str = "…") -> str:
    if not text:
        return ""
    return text if len(text) <= maximum_characters else text[: maximum_characters - len(suffix)] + suffix


def slugify(text: str, maximum_length: int = 60) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:maximum_length]
