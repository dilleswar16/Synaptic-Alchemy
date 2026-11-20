"""keigan/ai/author_labels.py: chat author names are replaced by placeholders before a model sees them (V12)."""

from __future__ import annotations

from keigan.ai.author_labels import AuthorAliases, mask_author_name, mask_known_names
from keigan.utils.pii_masker import PiiMasker


def test_the_same_person_always_gets_the_same_placeholder() -> None:
    masker = PiiMasker()
    assert mask_author_name(masker, "Rui Reader") == "<PERSON_1>"
    assert mask_author_name(masker, "Aiko AppAdmin") == "<PERSON_2>"
    assert mask_author_name(masker, "rui reader") == "<PERSON_1>"


def test_an_unknown_author_is_called_participant() -> None:
    assert mask_author_name(PiiMasker(), None) == "Participant"


def test_names_inside_other_text_are_replaced_as_whole_words_in_any_case() -> None:
    masker = PiiMasker()
    masked = mask_known_names(masker, "Rui Reader restarted it; thanks, rui reader. Ruined plans stay.", {"Rui Reader"})
    assert masked == "<PERSON_1> restarted it; thanks, <PERSON_1>. Ruined plans stay."


def test_very_short_names_are_not_replaced_because_they_would_match_inside_words() -> None:
    assert mask_known_names(PiiMasker(), "Al is on it", {"Al"}) == "Al is on it"


def test_aliases_can_restore_the_names_for_display() -> None:
    aliases = AuthorAliases(PiiMasker())
    line = f"{aliases.alias('Rui Reader')}: restarted the pods"
    assert line == "<PERSON_1>: restarted the pods"
    assert aliases.restore_names("<PERSON_1> restarted the pods") == "Rui Reader restarted the pods"
