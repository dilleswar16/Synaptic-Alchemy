"""Turns a command template and its checked values into the text a person copies (spec 33, 4.5).

Code, not the model, decides how a value appears: bare when it needs no quotes, in single quotes otherwise. The same template renders for bash and PowerShell. A slot with no usable value
becomes a ``missing_value`` segment (the screen shows an input there) and the command has no text until it is filled. A value that needs quotes may not touch literal text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from keigan.ai.fix_command_shape import SLOT_PATTERN, FixWithheldReason
from keigan.ai.fix_parameter_kinds import ValueRefusal, check_value, needs_quotes, quote

SegmentKind = Literal["literal", "value", "missing_value"]


@dataclass(frozen=True)
class ParameterValue:
    kind: str
    value: str | None  # None: not known


@dataclass(frozen=True)
class Segment:
    kind: SegmentKind
    text: str = ""
    parameter_name: str | None = None
    refusal: ValueRefusal | None = None  # why a value was not used: the value itself is never kept or shown


@dataclass(frozen=True)
class RenderedCommand:
    dialect: str
    segments: tuple[Segment, ...] = field(default_factory=tuple)
    withheld_reason: FixWithheldReason | None = None

    @property
    def text(self) -> str | None:
        """The command to copy, or None while a value is missing or when the command is withheld."""
        if self.withheld_reason is not None or any(segment.kind == "missing_value" for segment in self.segments):
            return None
        return "".join(segment.text for segment in self.segments)

    @property
    def missing_parameter_names(self) -> list[str]:
        return [segment.parameter_name for segment in self.segments if segment.kind == "missing_value" and segment.parameter_name]


def render_command(template: str, parameters: dict[str, ParameterValue], dialect: str) -> RenderedCommand:
    segments: list[Segment] = []
    position = 0
    for match in SLOT_PATTERN.finditer(template):
        name = match.group(1)
        if name not in parameters:
            return RenderedCommand(dialect, withheld_reason=FixWithheldReason.UNKNOWN_SLOT)
        literal_before, literal_after = template[position:match.start()], template[match.end():]
        if literal_before:
            segments.append(Segment("literal", literal_before))
        parameter = parameters[name]
        refusal = check_value(parameter.kind, parameter.value) if parameter.value is not None else None
        if parameter.value is None or refusal is not None:
            segments.append(Segment("missing_value", parameter_name=name, refusal=refusal))
        else:
            glued = literal_before[-1:] not in ("", " ") or literal_after[:1] not in ("", " ")
            if glued and needs_quotes(parameter.value):
                return RenderedCommand(dialect, withheld_reason=FixWithheldReason.VALUE_NOT_INSERTABLE)
            segments.append(Segment("value", quote(parameter.value), name))
        position = match.end()
    if template[position:]:
        segments.append(Segment("literal", template[position:]))
    return RenderedCommand(dialect, tuple(segments))
