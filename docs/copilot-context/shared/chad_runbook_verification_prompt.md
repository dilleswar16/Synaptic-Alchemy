# CHAD Runbook Quality Verification Prompt

**INSTRUCTIONS FOR USER:**
After GitHub Copilot generates the 5 CHAD runbook files in chat, paste the
prompt below as your **very next message** in the SAME Copilot Chat session.
Do NOT start a new session. Do NOT save the files first.
The prompt instructs Copilot to review its own output from the previous reply.

After Copilot replies, THEN save the corrected file versions to `knowledge/runbooks/`.

---

--- PROMPT START ---

In this conversation, you generated 5 CHAD runbook files:
- `chad-api-spec.md`
- `chad-dependencies.md`
- `chad-known-errors.md`
- `chad-service-topology.md`
- `chad-service-inventory.md`

Before I save them, review each one as a brutal SRE quality reviewer. Do NOT be lenient. If anything fails, output the **full corrected file content** immediately after the table — do not just describe the fix.

**For each of the 5 files, run these checks:**

### Check 1 — YAML Frontmatter Quality
- Does the file start with `---` and a `keywords: [...]` block?
- **Strict rule:** At least 2 keywords MUST be specific class names, endpoint paths, or exact service names extracted from the code (e.g. `HikariPool`, `PartnerController`, `/api/v1/payments`). Generic words like `error`, `api`, `timeout` alone do NOT count.
- **PASS:** 2+ specific code-derived keywords present. **FAIL:** Only generic terms or missing.

### Check 2 — No Invented Content
- Go back and verify every endpoint path, exception class name, dependency name, and service name against the actual workspace code you scanned.
- Flag every item that does NOT have a matching class, config entry, or manifest in the codebase as **[INVENTED - remove this]**.
- **PASS:** Zero invented items. **FAIL:** Any invented items found.

### Check 3 — Completeness
For `chad-api-spec.md`: List any `@RestController` classes you found in the code that are NOT covered in the generated file.
For `chad-dependencies.md`: List any `@FeignClient`, `RestTemplate`, `WebClient`, or `spring.cloud.azure.cosmos.*` config entries NOT covered.
For `chad-known-errors.md`: List any classes extending `RuntimeException` or `@ControllerAdvice` methods NOT covered.
For `chad-service-topology.md`: Are the Kubernetes namespace, deployment names, and pod labels taken from actual manifest files, not guessed?
For `chad-service-inventory.md`: Recount — how many `@SpringBootApplication` classes and Maven `<module>` entries exist? Does the count match what was generated?

### Check 4 — SRE Actionability (Zero Tolerance)
Every failure mode entry MUST have a specific action. These are AUTOMATIC FAILs:
- "Check the logs" → too vague
- "Restart the pod" with no condition → too vague
- "Contact the team" with no team name → too vague

A PASSING action looks like: "If `CosmosException` status 429 → open Azure Portal → Cosmos DB account → Data Explorer → scale RU/s on the `[container-name]` container. Do NOT restart the pod."

### Check 5 — Generate catalog.json Entries
Do NOT check if entries exist — they don't yet. Instead, generate the exact JSON entries I need to add to `knowledge/runbooks/catalog.json` for all 5 files. Use this format:
```json
{
  "keyword": "chad-known-errors",
  "title": "CHAD Known Application Errors",
  "file": "runbooks/chad-known-errors.md",
  "match_patterns": ["<use real class names and log strings you found in code>"]
}
```
Output all 5 entries as a single JSON array I can paste directly.

---

**OUTPUT FORMAT — follow this exactly:**

For each file, one table:

| Check | Result | Issue Found |
|-------|--------|-------------|
| Frontmatter quality | PASS/FAIL | detail |
| No invented content | PASS/FAIL | list [INVENTED] items or "none" |
| Completeness | PASS/FAIL | list missing items or "complete" |
| SRE Actionability | PASS/FAIL | list vague actions or "all specific" |

Then:
1. If any check FAILED — output the **complete corrected file content** for that file.
2. Output the **catalog.json entries** for all 5 files as a JSON array.

--- PROMPT END ---
