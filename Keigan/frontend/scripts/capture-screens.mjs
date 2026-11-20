// Visual smoke test: signs in through the API, opens every main screen in headless Edge, records console and page
// errors, and saves full-page screenshots.
// Usage: node scripts/capture-screens.mjs --web http://localhost:5180 --api http://localhost:8010 --out <folder> [--user upn] [--theme light|dark] [--only /alerts,/slo]
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { chromium } from "playwright-core";

const argumentValue = (name, fallback) => {
  const index = process.argv.indexOf(`--${name}`);
  return index > -1 ? process.argv[index + 1] : fallback;
};
const webBaseUrl = argumentValue("web", "http://localhost:5173");
const apiBaseUrl = argumentValue("api", "http://localhost:8000");
const outputDirectory = argumentValue("out", "screenshots");
const userPrincipalName = argumentValue("user", "keigan.admin@keigan.local");
const colorScheme = argumentValue("theme", "light");
const onlyPaths = argumentValue("only", "").split(",").filter(Boolean);
mkdirSync(outputDirectory, { recursive: true });

async function callApi(path, accessToken, init = {}) {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}), ...(init.headers ?? {}) },
  });
  if (!response.ok) throw new Error(`${path} → HTTP ${response.status}`);
  return response.json();
}

const signIn = await callApi("/api/auth/local-sign-in", null, { method: "POST", body: JSON.stringify({ userPrincipalName }) });
const accessToken = signIn.accessToken;
const listOf = (body) => (Array.isArray(body) ? body : body.items ?? []);
const applications = listOf(await callApi("/api/applications?pageSize=200", accessToken));
const claimsApplication = applications.find((application) => application.applicationCode === "CLMJP") ?? applications[0];
const investigations = listOf(await callApi("/api/investigations?pageSize=5", accessToken));
const investigationId = investigations[0]?.investigationId;

const routes = [
  ["home", "/"],
  ["incident-room", "/incidents"],
  ...["rca", "hypotheses", "evidence", "blast", "timeline", "alerts", "communications", "postmortem", "teams"].map((tabKey) => [
    `investigation-${tabKey}`,
    investigationId ? `/investigations/${investigationId}?tab=${tabKey}` : null,
  ]),
  ["alerts", "/alerts"],
  ["slo", "/slo"],
  ["intelligence", "/intelligence"],
  ["chat", "/chat"],
  ["applications", "/applications"],
  ...["components", "services", "log_tools", "knowledge", "topology", "runbooks", "incidents", "slo", "notifications", "access", "review"].map((stepKey) => [
    `workspace-${stepKey}`,
    claimsApplication ? `/applications/${claimsApplication.applicationId}/${stepKey}` : null,
  ]),
  ["admin-settings", "/administration/settings"],
  ["admin-usage", "/administration/usage"],
  ["admin-outbox", "/administration/outbox"],
  ["design-system", "/design-system"],
].filter(([, path]) => path && (onlyPaths.length === 0 || onlyPaths.some((onlyPath) => path === onlyPath || (onlyPath !== "/" && path.startsWith(onlyPath)))));

const browser = await chromium.launch({ channel: "msedge", headless: true });
const viewportWidth = Number(argumentValue("width", "1440"));
const context = await browser.newContext({ viewport: { width: viewportWidth, height: 900 }, colorScheme, locale: argumentValue("locale", "en-US") });
await context.addInitScript((session) => {
  window.sessionStorage.setItem("keigan.localSession", JSON.stringify(session));
}, { accessToken, expiresAt: signIn.expiresAt });

const report = [];
for (const [screenName, path] of routes) {
  const page = await context.newPage();
  const problems = [];
  page.on("console", (message) => message.type() === "error" && problems.push(`console: ${message.text().slice(0, 300)}`));
  page.on("pageerror", (error) => problems.push(`pageerror: ${String(error).slice(0, 300)}`));
  page.on("response", (response) => response.url().includes("/api/") && response.status() >= 400 && problems.push(`api ${response.status()}: ${response.url().replace(webBaseUrl, "")}`));
  try {
    await page.goto(`${webBaseUrl}${path}`, { waitUntil: "networkidle", timeout: 30000 });
    await page.waitForTimeout(Number(argumentValue("wait", "1200")));
  } catch (navigationError) {
    problems.push(`navigation: ${String(navigationError).slice(0, 200)}`);
  }
  const screenshotPath = join(outputDirectory, `${screenName}-${colorScheme}${viewportWidth === 1440 ? "" : `-${viewportWidth}`}.png`);
  await page.screenshot({ path: screenshotPath, fullPage: true });
  // The design-system page shows the error-state component on purpose.
  const visibleErrorText = path === "/design-system" ? 0 : await page.locator("text=/something went wrong|failed to load|couldn't load/i").count();
  if (visibleErrorText) problems.push(`visible error message on screen (${visibleErrorText})`);
  report.push({ screenName, path, screenshotPath, problems });
  console.log(`${problems.length ? "✗" : "✓"} ${screenName.padEnd(28)} ${problems.length} problem(s)`);
  await page.close();
}
await browser.close();
writeFileSync(join(outputDirectory, `report-${colorScheme}.json`), JSON.stringify(report, null, 2));
const failingScreens = report.filter((entry) => entry.problems.length);
for (const entry of failingScreens) console.log(`\n${entry.screenName} (${entry.path})\n  - ${entry.problems.slice(0, 6).join("\n  - ")}`);
