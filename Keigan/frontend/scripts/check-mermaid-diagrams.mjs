// Parses and renders every ```mermaid block in the given Markdown files with the real Mermaid library (headless Edge).
// Usage (from frontend/):  node scripts/check-mermaid-diagrams.mjs "../My Plans/13_SEQUENCE_DIAGRAMS.md" ... [--screenshots <folder>]
import { readFileSync, mkdirSync } from "node:fs";
import { basename, join } from "node:path";
import { chromium } from "playwright-core";

const MERMAID_URL = "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js";
const argumentsList = process.argv.slice(2);
const screenshotIndex = argumentsList.indexOf("--screenshots");
const screenshotFolder = screenshotIndex >= 0 ? argumentsList[screenshotIndex + 1] : null;
const markdownPaths = argumentsList.filter((value, index) => screenshotIndex < 0 || (index !== screenshotIndex && index !== screenshotIndex + 1));

const diagrams = markdownPaths.flatMap((markdownPath) =>
  [...readFileSync(markdownPath, "utf8").replace(/\r\n/g, "\n").matchAll(/```mermaid\n([\s\S]*?)```/g)].map((match, position) => ({
    label: `${basename(markdownPath)} #${position + 1}`,
    code: match[1],
  })),
);

const browser = await chromium.launch({ channel: "msedge", headless: true });
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
await page.setContent(`<html><body style="background:#fff"><div id="target"></div><script src="${MERMAID_URL}"></script></body></html>`);
await page.waitForFunction(() => typeof window.mermaid !== "undefined", null, { timeout: 30000 });
await page.evaluate(() => window.mermaid.initialize({ startOnLoad: false, securityLevel: "strict", maxTextSize: 200000, maxEdges: 2000 }));
if (screenshotFolder) mkdirSync(screenshotFolder, { recursive: true });

let failureCount = 0;
for (const [index, diagram] of diagrams.entries()) {
  const result = await page.evaluate(async ({ code, index }) => {
    try {
      await window.mermaid.parse(code);
      const { svg } = await window.mermaid.render(`diagram${index}`, code);
      document.getElementById("target").innerHTML = svg;
      const box = document.querySelector("#target svg").getBoundingClientRect();
      return { ok: true, width: Math.round(box.width), height: Math.round(box.height) };
    } catch (error) {
      return { ok: false, message: String(error?.message ?? error).slice(0, 400) };
    }
  }, { code: diagram.code, index });
  if (result.ok) {
    console.log(`ok    ${diagram.label}  (${result.width}x${result.height})`);
    if (screenshotFolder) {
      const fileName = `${diagram.label.replace(/[^a-z0-9]+/gi, "_")}.png`;
      await page.locator("#target svg").screenshot({ path: join(screenshotFolder, fileName) });
    }
  } else {
    failureCount += 1;
    console.log(`FAIL  ${diagram.label}\n      ${result.message}`);
  }
}
await browser.close();
console.log(`${diagrams.length} diagrams, ${failureCount} failed`);
process.exit(failureCount ? 1 : 0);
