"""keigan/services/postmortem_action_items.py: the document's table is a rendering of the rows (spec 29, 4.4)."""

from __future__ import annotations

from datetime import date

from keigan.entities.action_item_entities import ActionItem
from keigan.services.postmortem_action_items import NO_ACTION_ITEMS_TEXT, render_action_items_table, replace_action_items_section


def item(title: str, role: str | None = None, owner_id: str | None = None) -> ActionItem:
    return ActionItem(item_title=title, suggested_owner_role_text=role, owner_stakeholder_id=owner_id, due_on=date(2026, 12, 1), action_type="prevent", action_priority="top")


def test_no_items_renders_the_plain_sentence() -> None:
    assert render_action_items_table([], {}) == NO_ACTION_ITEMS_TEXT


def test_the_table_shows_the_owners_role_never_the_person_and_falls_back_to_the_suggested_role() -> None:
    table = render_action_items_table([item("Add alert", role="SRE team", owner_id="s1"), item("Fix limit", role="Platform team"), item("Nobody yet")], {"s1": "sre"})
    assert "| Add alert | sre | 2026-12-01 | prevent | top |" in table
    assert "| Fix limit | Platform team |" in table and "| Nobody yet | Unassigned |" in table


def test_a_pipe_in_a_title_cannot_break_the_table() -> None:
    assert "| a / b |" in render_action_items_table([item("a | b")], {})


def test_the_action_items_section_is_replaced_and_its_neighbours_are_kept() -> None:
    markdown = "# T\n\n## What could be improved\n- x\n\n## Action items\n| old |\n\n## Lessons learned\n- y\n"
    replaced = replace_action_items_section(markdown, "NEW TABLE")
    assert "NEW TABLE" in replaced and "| old |" not in replaced and "## What could be improved\n- x" in replaced and "## Lessons learned\n- y" in replaced


def test_a_document_without_the_section_gets_it_appended() -> None:
    assert replace_action_items_section("# T\n\ntext\n", "NEW").endswith("## Action items\nNEW\n")


def test_the_last_section_is_replaced_to_the_end_of_the_document() -> None:
    assert replace_action_items_section("# T\n\n## Action items\nold\nmore old\n", "NEW") == "# T\n\n## Action items\nNEW\n\n"
