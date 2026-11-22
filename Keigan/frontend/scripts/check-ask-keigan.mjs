// Browser check of Ask Keigan in the investigation panel (spec 23, section 12.3, the investigation-panel steps, phases 1 and 2): asks questions, watches the
// tool cards run and finish, follows a citation, opens the details and the full output, copies the answer with its sources, flips "Show tool details", checks
// the presentations of the SLO, change, runbook and application-map tools, a failing tool, Stop (before the first frame and after the first tool call, with
// the server's run read back to see that it was cancelled), the 409 an answer already running gives, reloads and finds the earlier exchange again, and checks
// the keyboard (Esc closes the panel when nothing runs; on a phone the panel is a modal dialog that keeps Tab inside) and the touch targets.
// Needs a backend with LLM_PROVIDER=mock, TELEMETRY_MODE=simulated and the demo seed, and the web app (the Vite dev server proxies /api to the backend).
// The offline model answers in a few hundred milliseconds, too fast to press a button in, so the page's `fetch` of the answer stream is wrapped (see
// `streamPlanScript`): it hands the browser the same frames, one at a time, and can hold one back or press Stop or Esc just before the browser reads it. The
// server is not slowed: what is checked afterwards (the run's status) is the server's own.
// A step is reported as passed, FAILED or SKIPPED (not checked, with the reason); a skipped step is not a pass and shows in the summary.
// Usage: node scripts/check-ask-keigan.mjs --web http://localhost:5173 --api http://localhost:8000 [--user upn] [--theme light|dark] [--width 1440] [--out folder]
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { chromium } from "playwright-core";

const argumentValue = (name, fallback) => {
  const index = process.argv.indexOf(`--${name}`);
  return index > -1 ? process.argv[index + 1] : fallback;
};
const webBaseUrl = argumentValue("web", "http://localhost:5173");
const apiBaseUrl = argumentValue("api", "http://localhost:8000");
const userPrincipalName = argumentValue("user", "rui.reader@keigan.local");
const colorScheme = argumentValue("theme", "light");
const viewportWidth = Number(argumentValue("width", "1440"));
const outputDirectory = argumentValue("out", "screenshots");
const applicationNameFragment = argumentValue("application", "Claims Processing");
const cardTimeoutMilliseconds = 10_000;
/** How long the stream holds back the frame a step wants to see the Running state of. */
const holdMilliseconds = 2_500;
/** How long the screen has to show a stopped run: the cancel, then one poll of the stored run. */
const stoppedTimeoutMilliseconds = 8_000;
/** The panel is a full-screen modal sheet below this width (Tailwind `sm`, 40 rem). */
const phoneMaximumWidth = 640;
/** Spec 8.8: targets are at least 44 px on a phone. */
const touchTargetMinimumPixels = 44;
const isPhone = viewportWidth < phoneMaximumWidth;
const detailsPreferenceKey = "keigan.chat.showToolDetails";
mkdirSync(outputDirectory, { recursive: true });

const results = [];
function record(stepName, isPassed, detail = "") {
  results.push({ stepName, status: isPassed ? "passed" : "failed", detail });
  console.log(`${isPassed ? "✓" : "✗ FAILED"} ${stepName}${detail ? ` — ${detail}` : ""}`);
}
/** A step that could not be checked here: it is not a pass, and the summary counts it. */
function skip(stepName, reason) {
  results.push({ stepName, status: "skipped", detail: reason });
  console.log(`- SKIPPED ${stepName} — ${reason}`);
}

async function callApi(path, accessToken, init = {}) {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}) },
  });
  if (!response.ok) throw new Error(`${path} → HTTP ${response.status}`);
  return response.json();
}

const signIn = await callApi("/api/auth/local-sign-in", null, { method: "POST", body: JSON.stringify({ userPrincipalName }) });
const investigations = await callApi("/api/investigations?pageSize=50", signIn.accessToken);
const investigationList = Array.isArray(investigations) ? investigations : investigations.items ?? [];
const investigation = investigationList.find((item) => JSON.stringify(item).includes(applicationNameFragment));
if (!investigation) throw new Error(`No investigation of "${applicationNameFragment}" is readable by ${userPrincipalName}: is the demo data seeded?`);
const investigationUrl = `${webBaseUrl}/investigations/${investigation.investigationId}`;
const investigationDetail = await callApi(`/api/investigations/${investigation.investigationId}`, signIn.accessToken);
const matchedRunbook = investigationDetail.matchedRunbooks?.[0] ?? null;
const openInvestigationConversation = () =>
  callApi("/api/chat/conversations", signIn.accessToken, { method: "POST", body: JSON.stringify({ conversationScope: "investigation", investigationId: investigation.investigationId }) });
// Start from an empty conversation: the investigation chat of this user is opened (created when missing) and deleted, and the page creates a new one.
const existingConversation = await openInvestigationConversation();
await fetch(`${apiBaseUrl}/api/chat/conversations/${existingConversation.conversationId}`, { method: "DELETE", headers: { Authorization: `Bearer ${signIn.accessToken}` } });

/**
 * Wraps `fetch` for the answer stream when `window.__streamPlan` is set (for one request): the frames come through one by one, unchanged, and the plan may
 * hold one back (`holdBefore` an event name), press Stop or Esc just before the browser reads one (`stopBefore`, `escapeBefore`) or end the stream after one
 * (`endAfter`: the connection dropped, the server's run goes on). Without a plan nothing changes.
 */
const streamPlanScript = () => {
  const originalFetch = window.fetch.bind(window);
  const encoder = new TextEncoder();
  const decoder = new TextDecoder();
  window.fetch = async (input, init) => {
    const response = await originalFetch(input, init);
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const plan = window.__streamPlan;
    if (!plan || !/\/chat\/conversations\/[^/]+\/answers$/.test(url) || !response.body) return response;
    window.__streamPlan = null;
    const reader = response.body.getReader();
    const frames = [];
    let bufferedText = "";
    let isSourceDone = false;
    const stream = new ReadableStream({
      async pull(controller) {
        while (frames.length === 0 && !isSourceDone) {
          const chunk = await reader.read();
          if (chunk.done) {
            isSourceDone = true;
            break;
          }
          bufferedText += decoder.decode(chunk.value, { stream: true }).replace(/\r\n/g, "\n");
          const parts = bufferedText.split("\n\n");
          bufferedText = parts.pop() ?? "";
          frames.push(...parts.map((part) => `${part}\n\n`));
        }
        const frame = frames.shift();
        if (frame === undefined) {
          controller.close();
          return;
        }
        const eventName = /^event: (.+)$/m.exec(frame)?.[1];
        if (plan.holdBefore === eventName) await new Promise((resolve) => setTimeout(resolve, plan.holdMilliseconds));
        if (plan.stopBefore === eventName) {
          // The Stop button appears when the screen has rendered the question as sent; wait for it (a busy machine renders late) rather than miss it.
          for (let attempt = 0; attempt < 100; attempt += 1) {
            const stopButton = [...document.querySelectorAll("button")].find((button) => button.textContent?.trim() === "Stop");
            if (stopButton) {
              stopButton.click();
              break;
            }
            await new Promise((resolve) => setTimeout(resolve, 20));
          }
        }
        if (plan.escapeBefore === eventName) document.querySelector('textarea[aria-label="Message Keigan"]')?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
        controller.enqueue(encoder.encode(frame));
        if (plan.endAfter === eventName) {
          controller.close();
          reader.cancel().catch(() => undefined);
        }
      },
      cancel: () => reader.cancel(),
    });
    return new Response(stream, { status: response.status, statusText: response.statusText, headers: response.headers });
  };
};

const browser = await chromium.launch({ channel: "msedge", headless: true });
const context = await browser.newContext({ viewport: { width: viewportWidth, height: 900 }, colorScheme, locale: "en-US", permissions: ["clipboard-read", "clipboard-write"] });
await context.addInitScript((session) => window.sessionStorage.setItem("keigan.localSession", JSON.stringify(session)), { accessToken: signIn.accessToken, expiresAt: signIn.expiresAt });
await context.addInitScript(streamPlanScript);
const page = await context.newPage();
const problems = [];
// Steps that make the server's answer fail on purpose (a stand-in 409, polls answered with 503) list the statuses here: those responses are not problems of the screen.
const expectedStatuses = new Set();
page.on("console", (message) => message.type() === "error" && ![...expectedStatuses].some((status) => message.text().includes(`status of ${status}`)) && problems.push(`console: ${message.text().slice(0, 300)}`));
page.on("pageerror", (error) => problems.push(`pageerror: ${String(error).slice(0, 300)}`));
page.on("response", (response) => response.url().includes("/api/") && response.status() >= 400 && !expectedStatuses.has(response.status()) && problems.push(`api ${response.status()}: ${response.url().replace(webBaseUrl, "")}`));

// The panel is a complementary region on a desktop and a modal dialog on a phone, so it is found by its name.
const panel = () => page.locator('[aria-label="Investigation chat"]');
const composer = () => panel().getByLabel("Message Keigan");
// The newest card with this label: an earlier exchange of the same conversation may have one too. The name is "{label}, {target}, {state}, {duration}, citation T#".
const toolCard = (label, stateWord = "") => panel().getByRole("button", { name: new RegExp(`^${label}, ${stateWord ? `.*${stateWord}` : ""}`) }).last();
const detailsSwitch = () => panel().getByRole("switch", { name: "Show tool details" });
const screenshotPath = (name) => join(outputDirectory, `ask-keigan-${name}-${colorScheme}-${viewportWidth}.png`);
const sendButton = () => panel().getByRole("button", { name: "Send" });

async function openPanel() {
  await page.goto(investigationUrl, { waitUntil: "networkidle", timeout: 30_000 });
  await page.getByRole("button", { name: "Ask Keigan" }).click();
  await composer().waitFor({ state: "visible", timeout: cardTimeoutMilliseconds });
}

/** Sets what the wrapped stream does for the next answer (see `streamPlanScript`). */
const planStream = (plan) => page.evaluate((streamPlan) => { window.__streamPlan = streamPlan; }, plan);

async function ask(questionText) {
  await composer().fill(questionText);
  await composer().press("Enter");
}

/** Asks and waits until the card has finished and the composer is usable again (the answer has been written). */
async function askAndWaitForCard(questionText, cardLabel) {
  await ask(questionText);
  await toolCard(cardLabel, "Done").waitFor({ state: "visible", timeout: cardTimeoutMilliseconds });
  await sendButton().waitFor({ state: "visible", timeout: cardTimeoutMilliseconds });
}

/** Opens the details of a card (in the sheet: the panel is too narrow to open them inside the card) and returns the dialog. */
async function openCardDetails(cardLabel) {
  await toolCard(cardLabel).click();
  const dialog = page.getByRole("dialog", { name: cardLabel, exact: true });
  await dialog.waitFor({ state: "visible", timeout: cardTimeoutMilliseconds });
  return dialog;
}

/** Esc closes the sheet; waits for its closing motion so the next click does not land on its overlay. */
async function closeSheet(dialog) {
  await page.keyboard.press("Escape");
  await dialog.waitFor({ state: "detached", timeout: cardTimeoutMilliseconds });
}

/** The newest run of this user's investigation conversation, as the server stores it (the same read the screen makes after a reload). */
async function readNewestRun() {
  const conversation = await openInvestigationConversation();
  const detail = await callApi(`/api/chat/conversations/${conversation.conversationId}`, signIn.accessToken);
  const runId = [...detail.messages].reverse().find((message) => message.messagePayload?.answerRunId)?.messagePayload.answerRunId;
  return runId ? callApi(`/api/chat/answer-runs/${runId}`, signIn.accessToken) : null;
}

const hasFocusInside = (locator) => locator.evaluate((element) => element.contains(document.activeElement));
const readStoredPreference = () => page.evaluate((key) => window.localStorage.getItem(key), detailsPreferenceKey);
const boundingHeight = async (locator) => (await locator.boundingBox())?.height ?? 0;
const boundingWidth = async (locator) => (await locator.boundingBox())?.width ?? 0;

try {
  // 1. The panel opens on the investigation page, takes focus, and is named for what it is.
  await openPanel();
  record("the panel opens with an empty conversation and a composer", await composer().isVisible());
  record("the panel is a modal dialog on a phone and a complementary region otherwise", (await panel().getAttribute("role")) === (isPhone ? "dialog" : "complementary") && (await panel().getAttribute("aria-modal")) === (isPhone ? "true" : null));
  record("opening the panel moves focus into it", await hasFocusInside(panel()));
  record("'Show tool details' is on by default", (await detailsSwitch().getAttribute("aria-checked")) === "true");

  // 2. The cards appear (Running, then Done), name their target and carry their citation. The frame that finishes the first call is held back, so the Running
  // state is on screen for long enough to be seen (spec 12.3 step 2).
  await planStream({ holdBefore: "tool.finished", holdMilliseconds });
  await ask("Show me evidence E2 and what the timeline says before it");
  const runningCard = toolCard("Opened evidence", "Running");
  const wasRunningShown = await runningCard.waitFor({ state: "visible", timeout: cardTimeoutMilliseconds }).then(() => true, () => false);
  const runningName = wasRunningShown ? ((await runningCard.getAttribute("aria-label")) ?? "") : "";
  const runningText = wasRunningShown ? await runningCard.innerText() : "";
  record("a card 'Opened evidence' shows Running (with the live timer left out of its accessible name) before it is Done", wasRunningShown && /Running/.test(runningName) && !/\d\s?s\b/.test(runningName) && /Running/.test(runningText), runningName);
  await toolCard("Opened evidence", "Done").waitFor({ state: "visible", timeout: cardTimeoutMilliseconds });
  await toolCard("Read the timeline", "Done").waitFor({ state: "visible", timeout: cardTimeoutMilliseconds });
  const evidenceCard = toolCard("Opened evidence");
  const evidenceCardName = (await evidenceCard.getAttribute("aria-label")) ?? "";
  const timelineCardName = (await toolCard("Read the timeline").getAttribute("aria-label")) ?? "";
  record("a card 'Opened evidence' is done, names the record it opened and carries T1", /Done/.test(evidenceCardName) && /E2/.test(evidenceCardName) && /citation T1/.test(evidenceCardName), evidenceCardName);
  record("a card 'Read the timeline' is done and carries T2", /Done/.test(timelineCardName) && /citation T2/.test(timelineCardName), timelineCardName);
  const describedBy = (await evidenceCard.getAttribute("aria-describedby")) ?? "";
  const description = describedBy ? await page.evaluate((ids) => ids.split(" ").map((id) => document.getElementById(id)?.textContent ?? "").join(" "), describedBy) : "";
  record("the card's summary is its accessible description, so a screen reader hears it too", description.trim().length > 0 && (await evidenceCard.innerText()).includes(description.trim().slice(0, 20)), description.slice(0, 120));
  await sendButton().waitFor({ state: "visible", timeout: cardTimeoutMilliseconds });

  // 3. The answer cites both calls; the citation focuses its card (its details open in a sheet, not by a citation click).
  const citationChip = panel().getByRole("button", { name: /^T2$/ }).first();
  await citationChip.waitFor({ state: "visible", timeout: cardTimeoutMilliseconds });
  if (isPhone) {
    record("on a phone a citation chip is at least 44 px high and wide", (await boundingHeight(citationChip)) >= touchTargetMinimumPixels && (await boundingWidth(citationChip)) >= touchTargetMinimumPixels, `${await boundingWidth(citationChip)} x ${await boundingHeight(citationChip)}`);
    const closeButton = panel().getByRole("button", { name: "Close" }).first();
    record("on a phone the panel's close button is at least 44 px", (await boundingHeight(closeButton)) >= touchTargetMinimumPixels && (await boundingWidth(closeButton)) >= touchTargetMinimumPixels, `${await boundingWidth(closeButton)} x ${await boundingHeight(closeButton)}`);
  }
  await citationChip.click();
  const timelineHeaderId = await toolCard("Read the timeline").getAttribute("id");
  // The card opens and takes focus a few renders after the click, so focus is waited for rather than read at once.
  const isCardFocused = await page.waitForFunction((headerId) => document.activeElement?.id === headerId, timelineHeaderId, { timeout: 3_000 }).then(() => true, () => false);
  record("clicking the citation T2 focuses the timeline card", isCardFocused);

  // 4. The details open in a sheet with the inputs and the result; "View full output" opens a second sheet; Esc closes them without closing the panel.
  const evidenceDetails = await openCardDetails("Opened evidence");
  record("a card's details open in a sheet with its inputs and its result", (await evidenceDetails.getByRole("heading", { name: "Inputs" }).count()) > 0 && (await evidenceDetails.getByRole("heading", { name: "Result" }).count()) > 0);
  // The investigation fixes the investigation id: it is shown with a lock and "Set by this investigation" (spec 12.3 step 7).
  const lockedInput = evidenceDetails.locator("span", { hasText: "Set by this investigation" }).filter({ has: page.locator("svg.lucide-lock") });
  record("an input the investigation fixed shows a lock icon and 'Set by this investigation'", (await lockedInput.count()) > 0);
  await evidenceDetails.getByRole("button", { name: "View full output" }).click();
  const outputDrawer = page.getByRole("dialog", { name: /full output/ });
  await outputDrawer.waitFor({ state: "visible", timeout: cardTimeoutMilliseconds });
  const hasStoredOutput = await outputDrawer.getByText("evidence_code").first().waitFor({ timeout: cardTimeoutMilliseconds }).then(() => true, () => false);
  record("'View full output' shows the result and the stored output", hasStoredOutput && (await outputDrawer.getByRole("heading", { name: "Result" }).count()) > 0);
  record("the result of an evidence record uses translated field names, not humanised English", (await outputDrawer.getByText("Signal strength").count()) > 0 && (await outputDrawer.getByText("Matching records").count()) > 0);
  await page.keyboard.press("Escape");
  await outputDrawer.waitFor({ state: "detached", timeout: cardTimeoutMilliseconds });
  await page.keyboard.press("Escape");
  await evidenceDetails.waitFor({ state: "detached", timeout: cardTimeoutMilliseconds });
  record("Esc inside the sheets closes them, returns focus to the card and leaves the panel open", (await composer().isVisible()) && (await page.evaluate(() => document.activeElement?.getAttribute("aria-haspopup") ?? "")) === "dialog");

  // 5. "Open in Keigan" goes to the record's page (the timeline card read an investigation).
  const timelineDetails = await openCardDetails("Read the timeline");
  const openLink = timelineDetails.getByRole("link", { name: /^Open in Keigan/ });
  const openHref = (await openLink.getAttribute("href").catch(() => null)) ?? "";
  record("a card whose record has a page offers 'Open in Keigan', whose name starts with the visible words", openHref === `/investigations/${investigation.investigationId}`, openHref || "no link");
  await closeSheet(timelineDetails);

  // 6. Copy answer with sources: the text holds the answer and a Sources list, and the copy is announced.
  const copyButton = panel().getByRole("button", { name: "Copy answer with sources" }).last();
  await copyButton.click();
  // The Windows clipboard turns line breaks into CR LF.
  const clipboardText = (await page.evaluate(() => navigator.clipboard.readText()).catch(() => "")).replaceAll("\r\n", "\n");
  record(
    "'Copy answer with sources' copies the answer and a Sources list naming each tool, its inputs and what it found",
    /\[T1\]/.test(clipboardText) && /\nSources\n\[T1\] Opened evidence/.test(clipboardText) && /Inputs: .*Evidence: E2/.test(clipboardText) && /\[T2\] Read the timeline/.test(clipboardText) && /Asked in Keigan on/.test(clipboardText),
    clipboardText.replace(/\n/g, " ⏎ ").slice(0, 900),
  );
  record("the copy is announced to screen readers", await panel().locator('[aria-live="polite"]', { hasText: "Copied" }).first().waitFor({ timeout: 2_000 }).then(() => true, () => false));

  // 7. An [E#] citation shows the evidence on the page.
  const evidenceChip = panel().getByRole("button", { name: /^E2$/ }).first();
  if (await evidenceChip.count()) {
    await evidenceChip.click();
    await page.waitForURL(/tab=evidence/, { timeout: cardTimeoutMilliseconds }).catch(() => undefined);
    record("an [E#] citation selects the evidence on the page", /tab=evidence/.test(page.url()), isPhone ? `the sheet closed: ${(await panel().count()) === 0}` : "");
    if (isPhone) await page.getByRole("button", { name: "Ask Keigan" }).click();
    await composer().waitFor({ state: "visible", timeout: cardTimeoutMilliseconds });
  } else {
    record("an [E#] citation selects the evidence on the page", false, "the answer has no E2 chip");
  }

  // 7b. An [R#] citation shows the matched runbook on the RCA tab. The offline planner never writes [R#], so the stored answer is amended on its way to the
  // browser: it gets the investigation's first matched runbook as R1. That checks the screen's wiring, not the planner.
  if (matchedRunbook) {
    const amendAnswer = async (route) => {
      const response = await route.fetch();
      const snapshot = await response.json();
      if (snapshot.answer) {
        snapshot.answer = {
          ...snapshot.answer,
          markdown: `${snapshot.answer.markdown} [R1]`,
          citations: [...snapshot.answer.citations, { code: "R1", runbookId: matchedRunbook.runbookId, title: matchedRunbook.runbookTitle }],
        };
      }
      await route.fulfill({ response, json: snapshot });
    };
    const answerRunUrl = /\/api\/chat\/answer-runs\/[0-9a-f-]+$/;
    await context.route(answerRunUrl, amendAnswer);
    await openPanel();
    await panel().getByRole("button", { name: /^R1$/ }).first().click({ timeout: cardTimeoutMilliseconds });
    const runbookItem = page.locator(`#runbook-${matchedRunbook.runbookId}`);
    await runbookItem.waitFor({ state: "visible", timeout: cardTimeoutMilliseconds }).catch(() => undefined);
    const isOutlined = await runbookItem.evaluate((element) => element.className.includes("ring-2")).catch(() => false);
    record("an [R#] citation shows the matched runbook, outlined, on the RCA tab", /tab=rca/.test(page.url()) && isOutlined, `${matchedRunbook.runbookTitle}; ${page.url().replace(webBaseUrl, "")}`);
    await context.unroute(answerRunUrl, amendAnswer);
    await openPanel();
  } else {
    skip("an [R#] citation shows the matched runbook, outlined, on the RCA tab", "this investigation has no matched runbook");
  }

  // 8. "Show tool details": off folds the steps to one line (a problem would still show a warning), a citation still opens its card, and the choice is kept.
  await detailsSwitch().click();
  const stepsButton = panel().getByRole("button", { name: /Keigan's steps/ }).last();
  record("turning 'Show tool details' off folds the steps to their header", (await stepsButton.getAttribute("aria-expanded")) === "false" && !(await toolCard("Opened evidence").isVisible()));
  record("a folded steps header does not point at a body that is not rendered", (await stepsButton.getAttribute("aria-controls")) === null);
  record("the choice is stored in this browser", (await readStoredPreference()) === "false");
  await openPanel();
  record("after a reload the switch is still off and the steps are still folded", (await detailsSwitch().getAttribute("aria-checked")) === "false" && !(await toolCard("Opened evidence").isVisible().catch(() => false)));
  await panel().getByRole("button", { name: /^T1$/ }).first().click();
  const evidenceHeaderId = await toolCard("Opened evidence").getAttribute("id");
  record("a citation still opens the folded steps and focuses its card", await page.waitForFunction((headerId) => document.activeElement?.id === headerId, evidenceHeaderId, { timeout: 3_000 }).then(() => true, () => false));
  await detailsSwitch().click();
  record("turning it on again opens the steps", (await readStoredPreference()) === "true" && (await toolCard("Opened evidence").isVisible()));

  // 9. The presentations of the Phase 2 tools: changes (list), SLO status (numbers), runbooks (passages), the application map (graph).
  await askAndWaitForCard("What changed in the last 24 hours?", "Checked recent changes");
  const changesDetails = await openCardDetails("Checked recent changes");
  record("recent changes: the card says what it found and its details list the changes", /change/i.test((await toolCard("Checked recent changes").innerText()).toLowerCase()) && (await changesDetails.getByRole("heading", { name: "Result" }).count()) > 0, (await toolCard("Checked recent changes").innerText()).replace(/\n/g, " | ").slice(0, 160));
  record("recent changes: the list uses translated field names", (await changesDetails.getByText("Kind of change").count()) > 0 || (await changesDetails.getByText("Changed by").count()) > 0);
  await closeSheet(changesDetails);

  await askAndWaitForCard("What is the SLO status?", "Checked SLO status");
  const sloDetails = await openCardDetails("Checked SLO status");
  await sloDetails.getByText("Compliance").first().waitFor({ timeout: cardTimeoutMilliseconds }).catch(() => undefined);
  record("SLO status: the details show a block per SLO with number tiles", (await sloDetails.getByText("Compliance").count()) > 0 && (await sloDetails.getByText("Burn rate (6 h)").count()) > 0);
  await page.screenshot({ path: screenshotPath("metrics") });
  await closeSheet(sloDetails);

  await askAndWaitForCard("What is the runbook for a database connection failure?", "Looked for runbooks");
  const runbookDetails = await openCardDetails("Looked for runbooks");
  record("runbooks: the details show titled excerpts with a match score", (await runbookDetails.getByText(/Match \d+/).count()) > 0 || (await runbookDetails.locator("article").count()) > 0);
  const runbookLink = runbookDetails.getByRole("link", { name: /^Open in Keigan/ });
  record("runbooks: 'Open in Keigan' goes to the application's runbooks", /\/applications\/[^/]+\/runbooks$/.test((await runbookLink.getAttribute("href").catch(() => null)) ?? ""));
  await closeSheet(runbookDetails);

  await askAndWaitForCard("Show the application map: what does this application depend on?", "Read the application map");
  const mapDetails = await openCardDetails("Read the application map");
  await mapDetails.getByRole("heading", { name: /^Components/ }).waitFor({ timeout: cardTimeoutMilliseconds }).catch(() => undefined);
  record("application map: the details list components and connections", (await mapDetails.getByRole("heading", { name: /^Components/ }).count()) > 0 && (await mapDetails.getByRole("heading", { name: /^Connections/ }).count()) > 0);
  await page.screenshot({ path: screenshotPath("graph") });
  await closeSheet(mapDetails);

  // 9b. A log query on simulated telemetry says so on its card, and the card reads that from the server's own flags (not from a preview the server may cut).
  await askAndWaitForCard("How many failed requests did claims-api have in the last 24 hours?", "Queried the logs");
  const logCard = toolCard("Queried the logs");
  const logCardText = await logCard.innerText();
  record("a log query on simulated telemetry shows the 'Simulated data' flag, which the screen reader hears with the card", /Simulated data/.test(logCardText) && ((await logCard.getAttribute("aria-describedby")) ?? "").split(" ").length >= 2, logCardText.replace(/\n/g, " | ").slice(0, 200));
  await page.screenshot({ path: screenshotPath("log-query") });

  // 9c. A tool that fails does not fail the answer: its card says Failed with the server's own message, and the screen reader hears that message.
  await ask("Show me evidence E99");
  await toolCard("Opened evidence", "(Failed|Not allowed|Invalid input)").waitFor({ state: "visible", timeout: cardTimeoutMilliseconds });
  await sendButton().waitFor({ state: "visible", timeout: cardTimeoutMilliseconds });
  const failedCard = toolCard("Opened evidence", "(Failed|Not allowed|Invalid input)");
  const failedText = await failedCard.innerText();
  record("a failing tool call shows a Failed card with the server's message, and the run still ends with the composer usable", /Failed|Not allowed|Invalid input/.test(failedText) && failedText.split("\n").length >= 3 && (await sendButton().isVisible()), failedText.replace(/\n/g, " | ").slice(0, 200));
  await page.screenshot({ path: screenshotPath("tool-failed") });

  // 9d. The connection drops after the first frame and the server's answers to the polls fail (spec 7.5). The run goes on at the server, so the screen must keep
  // asking: a 503 and a 429 are retried and the answer still arrives.
  const snapshotUrl = /\/api\/chat\/answer-runs\/[0-9a-f-]+$/;
  let failedPolls = 0;
  const failFirstPolls = (route) => (failedPolls++ < 2 ? route.fulfill({ status: failedPolls === 1 ? 503 : 429, contentType: "application/problem+json", body: JSON.stringify({ title: "Not now", status: failedPolls === 1 ? 503 : 429 }) }) : route.continue());
  expectedStatuses.add(503).add(429);
  await context.route(snapshotUrl, failFirstPolls);
  await planStream({ endAfter: "answer.started" });
  await ask("What is the SLO status?");
  const recovered = await toolCard("Checked SLO status", "Done").waitFor({ state: "visible", timeout: 20_000 }).then(() => true, () => false);
  await sendButton().waitFor({ state: "visible", timeout: cardTimeoutMilliseconds });
  await context.unroute(snapshotUrl, failFirstPolls);
  expectedStatuses.delete(503);
  expectedStatuses.delete(429);
  record("a 503 and a 429 while following a run are retried: the answer still arrives, with no failure shown and the composer is Send again", recovered && failedPolls >= 3 && (await panel().getByText(/connection was lost/).count()) === 0, `${failedPolls} polls`);

  // 9e. Polls that keep failing: after the bounded number of tries the screen stops waiting, says the connection was lost, offers "Check again" and the composer
  // is no longer in the Stop state; once the server answers, "Check again" brings the finished answer.
  const failEveryPoll = (route) => route.fulfill({ status: 503, contentType: "application/problem+json", body: JSON.stringify({ title: "Unavailable", status: 503 }) });
  expectedStatuses.add(503);
  await context.route(snapshotUrl, failEveryPoll);
  await planStream({ endAfter: "answer.started" });
  await ask("What changed in the last 24 hours?");
  const lostNotice = panel().getByRole("alert").filter({ hasText: "connection was lost" });
  const wasGivenUp = await lostNotice.waitFor({ timeout: 60_000 }).then(() => true, () => false);
  const checkAgain = lostNotice.getByRole("button", { name: "Check again" });
  record("when polls keep failing the screen gives up with 'the connection was lost' and a 'Check again' action, and the composer is Send again, not an endless Stop", wasGivenUp && (await checkAgain.isVisible()) && (await sendButton().isVisible()));
  await page.screenshot({ path: screenshotPath("connection-lost") });
  await context.unroute(snapshotUrl, failEveryPoll);
  expectedStatuses.delete(503);
  if (wasGivenUp) await checkAgain.click();
  const caughtUp = await toolCard("Checked recent changes", "Done").waitFor({ state: "visible", timeout: 20_000 }).then(() => true, () => false);
  await sendButton().waitFor({ state: "visible", timeout: 20_000 });
  record("'Check again' follows the run again and shows the finished answer, and the notice goes away", caughtUp && (await lostNotice.count()) === 0);

  // 10. Stop. The frames reach the screen one at a time and Stop is pressed just before the screen reads one, so the answer is always still running for it.
  // 10a. Before the first frame: the screen waits for the run's id, then cancels it, so the server's run does not go on (spec 7.5).
  await planStream({ stopBefore: "answer.started" });
  await ask("Show me evidence E1 and what the timeline says");
  const stoppedEarly = await panel().getByText("Stopped by you").last().waitFor({ timeout: stoppedTimeoutMilliseconds }).then(() => true, () => false);
  await sendButton().waitFor({ state: "visible", timeout: cardTimeoutMilliseconds });
  const earlyRun = await readNewestRun();
  record("Stop pressed before the first frame ends the run: 'Stopped by you' is shown (also when no step ran), the composer is Send again and the server's run is cancelled", stoppedEarly && (await sendButton().isVisible()) && earlyRun?.status === "cancelled" && earlyRun.stopReason === "cancelled_by_user", `server run: ${earlyRun?.status}/${earlyRun?.stopReason}`);

  // 10b. After the first tool call started, with Esc in the composer (spec 12.3 step 6).
  await planStream({ escapeBefore: "tool.started" });
  await ask("Show me evidence E2 and what the timeline says");
  const stoppedLate = await panel().getByText("Stopped by you").last().waitFor({ timeout: stoppedTimeoutMilliseconds }).then(() => true, () => false);
  await sendButton().waitFor({ state: "visible", timeout: cardTimeoutMilliseconds });
  const lateRun = await readNewestRun();
  record("Esc after the first tool call started stops the answer ('Stopped by you'), does not close the panel, and the server's run is cancelled", stoppedLate && (await composer().isVisible()) && (await composer().isEnabled()) && lateRun?.status === "cancelled", `server run: ${lateRun?.status}/${lateRun?.stopReason}`);
  await page.screenshot({ path: screenshotPath("stopped") });

  // 10c. An answer already running in the conversation (409 answer_in_progress with the other run's id): the screen says so and offers to stop that run. The
  // server's answer is a stand-in (the offline answer is too short to still be running); the run id is a real one, and its cancel is the server's own.
  const otherRun = lateRun;
  if (otherRun) {
    const answersUrl = /\/api\/chat\/conversations\/[^/]+\/answers$/;
    const refuseAsRunning = (route) =>
      route.fulfill({
        status: 409,
        contentType: "application/problem+json",
        body: JSON.stringify({ title: "An answer is already running", status: 409, errorCode: "answer_in_progress", detail: "Keigan is still answering your previous question.", answerRunId: otherRun.answerRunId }),
      });
    expectedStatuses.add(409);
    await context.route(answersUrl, refuseAsRunning);
    await ask("What changed in the last hour?");
    const conflictBanner = panel().getByRole("alert").filter({ hasText: "still answering" });
    const isConflictShown = await conflictBanner.waitFor({ timeout: cardTimeoutMilliseconds }).then(() => true, () => false);
    const stopOther = conflictBanner.getByRole("button", { name: "Stop" });
    // The run has ended, so the server answers the cancel with 409 answer_not_running, which the screen treats as "stopped"; the response is awaited before the 409 is no longer expected.
    const cancelResponse = page.waitForResponse((response) => response.url().endsWith(`/answer-runs/${otherRun.answerRunId}/cancel`), { timeout: cardTimeoutMilliseconds }).then(() => true, () => false);
    if (isConflictShown) await stopOther.click();
    record("a 409 'answer already running' is shown with a Stop for the other run, which cancels that run by the id the server named", isConflictShown && (await cancelResponse));
    await context.unroute(answersUrl, refuseAsRunning);
    expectedStatuses.delete(409);
  } else {
    record("a 409 'answer already running' is shown with a Stop for the other run", false, "no earlier run to name");
  }

  // 11. A reload brings back the earlier exchange and its trace (AC-38), the stopped run included, without announcing old failures again.
  await openPanel();
  await toolCard("Opened evidence").waitFor({ state: "visible", timeout: cardTimeoutMilliseconds });
  const reloadedText = await panel().innerText();
  record("after a reload the panel shows the earlier question and its cards", /Show me evidence E2/.test(reloadedText) && (await toolCard("Opened evidence").count()) >= 1);
  record("after a reload a stopped run still says 'Stopped by you'", await panel().getByText("Stopped by you").first().waitFor({ timeout: cardTimeoutMilliseconds }).then(() => true, () => false));
  record("nothing in a reloaded conversation is announced as an alert", (await panel().getByRole("alert").count()) === 0);
  await page.screenshot({ path: screenshotPath("reloaded") });

  // 12. Keyboard: Esc closes the panel when nothing runs and focus returns to the launcher; on a phone Tab then stays inside the reopened sheet.
  await composer().focus();
  await page.keyboard.press("Escape");
  await panel().waitFor({ state: "detached", timeout: 3_000 }).catch(() => undefined);
  await page.waitForFunction(() => document.activeElement?.textContent?.trim() === "Ask Keigan", null, { timeout: 2_000 }).catch(() => undefined);
  const launcherFocused = await page.evaluate(() => document.activeElement?.textContent?.trim() ?? "");
  record("Esc with nothing running closes the panel and returns focus to 'Ask Keigan'", (await panel().count()) === 0 && launcherFocused === "Ask Keigan", `focus on "${launcherFocused}"`);
  if (isPhone) {
    await openPanel();
    await composer().focus();
    let staysInside = true;
    for (let pressCount = 0; pressCount < 40 && staysInside; pressCount += 1) {
      await page.keyboard.press("Tab");
      staysInside = await hasFocusInside(panel());
    }
    await page.keyboard.press("Shift+Tab");
    record("on a phone Tab and Shift+Tab stay inside the sheet", staysInside && (await hasFocusInside(panel())));
  }

  // 13. Layout and console.
  const hasHorizontalScroll = await page.evaluate(() => (document.scrollingElement?.scrollWidth ?? 0) > (document.scrollingElement?.clientWidth ?? 0));
  record("the page has no horizontal scroll", !hasHorizontalScroll);
} catch (error) {
  record("the check ran to the end", false, String(error).slice(0, 400));
  await page.screenshot({ path: screenshotPath("failure") }).catch(() => undefined);
}
record("no console errors, page errors or failing API calls", problems.length === 0, problems.slice(0, 5).join(" | "));
await browser.close();
const count = (status) => results.filter((result) => result.status === status).length;
console.log(`\n${count("passed")} passed, ${count("failed")} FAILED, ${count("skipped")} SKIPPED of ${results.length} steps (${colorScheme}, ${viewportWidth}px).`);
for (const skipped of results.filter((result) => result.status === "skipped")) console.log(`  skipped: ${skipped.stepName} — ${skipped.detail}`);
process.exit(count("failed") ? 1 : 0);
