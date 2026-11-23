# 36 — Diagrams in Ask Keigan answers (Mermaid)

Roadmap item 10 (`00_STATUS_AND_ROADMAP.md`). Written 2026-11-23 on branch `keigan-ui-ux`, with the build. Related: doc 23 (Ask Keigan), doc 06 (AI engine and prompt safety), doc 17 (security review: links and images).

## 1. Purpose and decisions

**Purpose.** A person asks Ask Keigan for an architecture, flow or sequence diagram and gets one drawn in the chat, not a wall of text. Also, the application map a tool returns can be seen as a picture, not only as two lists.

| # | Decision | Why |
|---|---|---|
| D1 | The model writes a fenced `mermaid` block in its answer; the browser draws it. No server-side drawing, no Mermaid MCP server. | The browser already draws it; a server renderer needs a headless browser and adds attack surface. |
| D2 | Drawn in Mermaid's **strict** security level with HTML labels off: no scripts, no click handlers, no links. The library loads only when a diagram appears (its own chunk). | The diagram text may be influenced by untrusted data (tool results, user text). |
| D3 | The server checks every `mermaid` block in an answer before it is shown. A block that fails is not dropped: its language is rewritten to `mermaid-withheld`, so the screen shows the source as code with a note saying why it was not drawn. | A silent drop hides what the model wrote; a failing check must not break the answer. |
| D4 | **Allowed**: `flowchart`/`graph`, `sequenceDiagram`, `stateDiagram-v2`, `erDiagram`, `classDiagram`, `timeline`. **Refused**: configuration directives (`%%{`), `click`, `href`, `call`, links (`://`), HTML tags (except `<br>`), `javascript:`, more than `ASK_KEIGAN_DIAGRAM_MAXIMUM_CHARACTERS` characters or `ASK_KEIGAN_DIAGRAM_MAXIMUM_LINES` lines, an unknown first line. | Each is either an injection path or a way to make a page unusable. |
| D5 | A drawn diagram is captioned "Drawn by Keigan's AI from this answer. Check it against the cited sources." and has "Show source" with a copy button. | A picture looks more certain than text; it must carry the same honesty as the text. |
| D6 | The prompt tells the model: draw only when asked or when a diagram is clearly the best answer; take names and connections from tool results only and cite them in the sentence after the diagram (a citation inside the diagram is not safe); short labels; no secrets, links or commands in a diagram; at most one diagram per answer unless asked. | Grounding, as for every other fact. |
| D7 | The application map tool's card gets a **Diagram** view drawn by code from the tool's own nodes and edges (no model involved), so the picture of the real map is exact. Free-form diagrams are illustrations (D5); this one is the data. | Two different levels of trust must not look the same: this one is captioned as drawn from the map. |
| D8 | Teams and email show the diagram's source as a code block (the Teams bot and the email renderer cannot draw Mermaid). | Honest fallback; the text is still readable. |

## 2. Server (`backend/keigan/ai/mermaid_diagram_check.py`)

- `check_diagram_source(source, maximum_characters, maximum_lines) -> DiagramProblem | None` (a `StrEnum`: `too_long`, `too_many_lines`, `unknown_type`, `directive`, `interaction`, `link`, `html`, `empty`).
- `withhold_unsafe_diagrams(markdown, maximum_characters, maximum_lines) -> str` rewrites each failing fenced block's language to `mermaid-withheld:<problem>`; passing blocks and every other fence are untouched.
- Called on each released paragraph in `AnswerTextStreamer._clean` and on the final answer in `ask_keigan_answer_assembler`, after the markdown sanitiser, so what streams and what is stored agree.
- Settings (settings, `.env`, `.env.example`, Helm, documentation test): `ASK_KEIGAN_DIAGRAM_MAXIMUM_CHARACTERS` 6000 (500 to 20000), `ASK_KEIGAN_DIAGRAM_MAXIMUM_LINES` 120 (10 to 500).
- Prompt `_ask_keigan_rules.md`: the rule of D6.

## 3. Screen

- `MarkdownView`'s code block draws `mermaid` blocks with `MermaidDiagram` (lazy import, strict mode, theme follows light and dark, text alternative from the first line, parse failure falls back to the source with a note) and shows `mermaid-withheld:<problem>` as code with the reason.
- `GraphOutput` (the application map card) gets a Diagram view from `graphDiagram.ts` (pure: node ids are generated, labels are quoted and cleaned, capped at 40 components).
- Strings in `common` (`mermaid.*`) and `chat` (`tool.graph.diagram*`), six locales.

## 4. Acceptance criteria

| # | Criterion | Check |
|---|---|---|
| AC-1 | Every allowed diagram type passes; each refused construct (D4) is withheld with its reason | unit |
| AC-2 | Only `mermaid` fences are touched; code in other fences is never rewritten; an unclosed fence is left alone | unit |
| AC-3 | A streamed answer and its stored final answer both carry the withheld marker for a bad block | integration |
| AC-4 | The size limits are settings and are documented where an operator looks | unit |
| AC-5 | The prompt tells the model the rules of D6 | unit (prompt text) |
| AC-6 | The topology diagram is generated by code: ids are not user text, a label with quotes, brackets or `-->` cannot change the structure | frontend unit (pure function) |

## 5. Not built / later

Diagrams from the incident timeline and blast radius as tools (the topology one is the pattern); a diagram in the exported PDF or in Teams as an image; localised category names inside diagrams; checking the diagram's connections against the cited tool results (the model's diagram is an illustration, D5); not seen in a browser.


## 6. Build notes (2026-11-23)

Built as designed, with these differences and findings:
- Added to D4: `$$` formulas are refused (`math`), because KaTeX has an open low advisory and answers have no use for formulas. Mermaid is **11.17.2**: the audit of 11.4.1 reported 8 high findings (in the library's dependencies); 2 low remain, both KaTeX.
- An unclosed fence is judged to the end of the text (the first design left it alone); the answer is released in whole paragraphs, so a fence is only ever open at the very end. The sanitiser used to close such a fence on the same line as the last code line; fixed (`output_sanitizer._render_leaf_block`).
- The shared cleaning is `ai/ask_keigan_answer_cleaning.clean_answer_markdown`, used by the streamer and the assembler; the engine test shows the streamed text and the stored answer agree.
- Prompts `ask_keigan_global` and `ask_keigan_investigation` are version 2 (the rule is in their shared fragment).
- Tests: `tests/unit/ai/test_mermaid_diagram_check.py` (32), stream, assembler, sanitiser and prompt tests, one engine test, `frontend/src/components/chat/graphDiagram.test.ts` (6, AC-6). Sample diagrams, including the generated map, were drawn in headless Edge with `frontend/scripts/check-mermaid-diagrams.mjs`.
- Frontend: `components/ui/MermaidDiagram.tsx` (`MermaidDiagram`, `WithheldDiagram`), the code block of `MarkdownView`, `components/chat/graphDiagram.ts` and the **Show as a diagram** view of the map card; strings in `common` (`mermaid.*`) and `chat` (`tool.graph.diagram*`), six locales. The library is its own lazy chunk (about 625 kB, 152 kB gzipped); the main bundle did not grow. The nginx policy needed no change (the library's inline styles are allowed by `style-src 'unsafe-inline'`).
- Not built: see section 5, plus: a citation code written as a node label (`A[E1]`) is read as a citation by the cleaner and may be removed; the offline model never draws a diagram; not seen in a browser; not tried on a real model for drawing quality.
