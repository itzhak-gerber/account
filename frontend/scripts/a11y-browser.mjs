// Accessibility check in a real browser (IS 5568 / WCAG 2.0 AA): opens every screen of the
// built app with sample API data, desktop and phone size, and runs axe including colour
// contrast, which jsdom cannot check. Usage: npm run build && npm run a11y:browser
import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

import { chromium } from "playwright";

import { fixtureBody, ME } from "../src/test/apiFixtures.ts";

const require = createRequire(import.meta.url);
const AXE = readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");
const PORT = 4179;
const BASE = `http://localhost:${PORT}`;
const SCREENS = [
  ["dashboard", "/"],
  ["documents", "/documents"],
  ["document", "/documents/d1"],
  ["new document", "/documents/new?type=tax_invoice"],
  ["customers", "/customers"],
  ["items", "/items"],
  ["inventory", "/inventory"],
  ["reports", "/reports"],
  ["notifications", "/notifications"],
  ["settings", "/settings"],
  ["data export", "/settings?tab=export"],
  ["profile", "/profile"],
  ["accessibility statement", "/accessibility"],
  ["onboarding", "/", { ...ME, memberships: [] }],
  ["two-factor required", "/", { ...ME, memberships: [], mfa: false }],
];
const SIZES = [
  ["desktop", { width: 1366, height: 900 }],
  ["phone", { width: 390, height: 844 }],
];

const server = spawn("npx", ["vite", "preview", "--port", String(PORT), "--strictPort"], {
  stdio: "ignore",
});
for (let i = 0; ; i++) {
  try {
    if ((await fetch(BASE)).ok) break;
  } catch {
    if (i > 100) throw new Error("preview server did not start");
  }
  await new Promise((r) => setTimeout(r, 200));
}

const browser = await chromium.launch(
  process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {},
);
let failures = 0;
try {
  for (const [size, viewport] of SIZES) {
    for (const [name, path, me] of SCREENS) {
      const page = await browser.newPage({ viewport, locale: "he-IL" });
      await page.route("**/api/v1/**", (route) =>
        route.fulfill({ json: fixtureBody(new URL(route.request().url()).pathname, me) }),
      );
      await page.goto(BASE + path);
      await page.locator("main h1, h1").first().waitFor();
      await page.waitForTimeout(500);
      await page.addScriptTag({ content: AXE });
      const violations = await page.evaluate(async () => {
        const result = await window.axe.run(document, {
          runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "best-practice"] },
        });
        return result.violations.map((v) => ({
          id: v.id,
          impact: v.impact,
          help: v.help,
          nodes: v.nodes.map(
            (n) => `${n.target.join(" ")}  ${n.failureSummary?.split("\n")[1] ?? ""}`,
          ),
        }));
      });
      const label = `${name} (${size})`;
      if (violations.length === 0) console.log(`ok    ${label}`);
      for (const v of violations) {
        failures++;
        console.log(`FAIL  ${label}: ${v.id} [${v.impact}] ${v.help}`);
        for (const n of v.nodes.slice(0, 5)) console.log(`        ${n}`);
      }
      await page.close();
    }
  }
} finally {
  await browser.close();
  server.kill();
}
process.exit(failures ? 1 : 0);
