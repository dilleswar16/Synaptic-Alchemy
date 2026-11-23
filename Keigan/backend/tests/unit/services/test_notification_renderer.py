"""keigan/services/notification_renderer.py: the last gate before an email or Teams card is sent (V8)."""

from __future__ import annotations

from keigan.services.notification_renderer import NotificationRenderer, markdown_to_safe_html

RENDERER = NotificationRenderer()


def test_html_body_has_no_links_or_images_to_hosts_that_are_not_allowed() -> None:
    body_html = markdown_to_safe_html("[a](https://evil.example/x) ![i](https://evil.example/i.png) https://evil.example/y")
    assert "href=\"https://evil.example" not in body_html
    assert "<img" not in body_html


def test_html_body_keeps_a_link_to_an_allowed_host_as_a_real_link() -> None:
    assert '<a href="https://portal.azure.com/x">open</a>' in markdown_to_safe_html("[open](https://portal.azure.com/x)")


def test_html_body_escapes_raw_html_and_shows_no_stray_backslashes() -> None:
    body_html = markdown_to_safe_html("<b>x</b> and snake_case")
    assert "&lt;b&gt;x&lt;/b&gt;" in body_html
    assert "\\" not in body_html


def test_an_override_subject_cannot_inject_a_header() -> None:
    rendered = RENDERER.render_email("progress_update", "en", "Claims", "Title", subject_override="[P2] Hello\r\nBcc: attacker@evil.example")
    assert "\n" not in rendered.subject_line and "\r" not in rendered.subject_line


def test_a_generated_subject_from_an_incident_title_is_one_line() -> None:
    rendered = RENDERER.render_email("incident_detected", "en", "Claims", "Title\r\nBcc: attacker@evil.example")
    assert "\n" not in rendered.subject_line


def test_the_card_summary_is_sanitised() -> None:
    card = RENDERER.render_card("preliminary_report", "en", "preliminary_report", "T", "[x](https://evil.example/z)", [("Incident", "INC1")])
    assert "](https://evil.example" not in str(card)


# ── Fenced code blocks (spec 33, AC-19): a suggested command must reach a technical-role email as code ──────────────────


def test_a_fenced_block_is_one_escaped_pre_code_block_and_leaves_no_stray_backticks() -> None:
    from keigan.services.notification_renderer import markdown_to_safe_html

    rendered = markdown_to_safe_html("Restart it.\n\n```bash\nkubectl get pods | grep <x> && echo \"a\"\n```\n\n- then check")
    assert rendered.count("<pre") == 1 and "<code>kubectl get pods | grep &lt;x&gt; &amp;&amp; echo &quot;a&quot;</code>" in rendered
    assert "`" not in rendered and "<ul" in rendered and "<p style=\"margin:6px 0;\">Restart it.</p>" in rendered


def test_nothing_inside_a_fence_is_formatted_and_an_unclosed_fence_still_shows_as_code() -> None:
    from keigan.services.notification_renderer import markdown_to_safe_html

    rendered = markdown_to_safe_html("```\n**not bold** `x` [a](https://example.com)\n")
    assert "<strong>" not in rendered and "<a href" not in rendered and rendered.count("<pre") == 1
