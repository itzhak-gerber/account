// Accessibility check in a real browser (IS 5568 / WCAG 2.0 AA): opens every screen of the
// built app with sample API data, desktop and phone size, in light mode, dark mode and with the
// largest text size, and runs axe including colour contrast, which jsdom cannot check. Also
// fails when a screen scrolls sideways (text must reflow when enlarged).
// Usage: npm run build && npm run a11y:browser   (A11Y_SHOTS=<dir> also saves screenshots)
import { spawn } from "node:child_process";
import { mkdirSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";

import { chromium } from "playwright";

import { fixtureBody, ME } from "../src/test/apiFixtures.ts";

const require = createRequire(import.meta.url);
const AXE = readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");
// The production Content-Security-Policy (from the nginx config): every screen must work under it.
const CSP = readFileSync(new URL("../deploy/default.conf.template", import.meta.url), "utf8").match(
  /Content-Security-Policy "([^"]+)"/,
)[1];
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
  ["purchase orders", "/purchasing"],
  ["goods receipts", "/purchasing?tab=receipts"],
  ["supplier invoices", "/purchasing?tab=invoices"],
  ["suppliers", "/purchasing?tab=suppliers"],
  ["reports", "/reports"],
  ["notifications", "/notifications"],
  ["settings", "/settings"],
  ["data export", "/settings?tab=export"],
  ["tax authority", "/settings?tab=ita"],
  ["profile", "/profile"],
  ["accessibility statement", "/accessibility"],
  ["onboarding", "/", { ...ME, memberships: [] }],
  ["two-factor required", "/", { ...ME, memberships: [], mfa: false }],
];
const SIZES = [
  ["desktop", { width: 1366, height: 900 }],
  ["phone", { width: 390, height: 844 }],
];
// The sample user follows the device theme, so the device's colour scheme picks the mode.
const MODES = [
  ["light", "light", {}],
  ["dark", "dark", {}],
  ["large text", "light", { text_size: "xlarge" }],
];
const SHOTS = process.env.A11Y_SHOTS;
if (SHOTS) mkdirSync(SHOTS, { recursive: true });

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
  for (const [mode, colorScheme, display] of MODES) {
    for (const [size, viewport] of SIZES) {
      for (const [name, path, screenMe] of SCREENS) {
        const base = screenMe ?? ME;
        const me = { ...base, user: { ...base.user, ...display } };
        const page = await browser.newPage({ viewport, locale: "he-IL", colorScheme });
        await page.route("**/api/v1/**", (route) =>
          route.fulfill({ json: fixtureBody(new URL(route.request().url()).pathname, me) }),
        );
        await page.route(
          (url) => url.origin === BASE && !url.pathname.startsWith("/api/"),
          async (route) => {
            if (route.request().resourceType() !== "document") return route.continue();
            const response = await route.fetch();
            await route.fulfill({
              response,
              headers: { ...response.headers(), "content-security-policy": CSP },
            });
          },
        );
        const blocked = [];
        page.on("console", (m) => {
          if (/Content Security Policy/i.test(m.text())) blocked.push(m.text().slice(0, 200));
        });
        await page.goto(BASE + path);
        await page.locator("main h1, h1").first().waitFor();
        await page.waitForTimeout(500);
        // Evaluated by the test driver, so the page's CSP (no inline scripts) does not apply.
        await page.evaluate(AXE);
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
        const label = `${name} (${size}, ${mode})`;
        const overflow = await page.evaluate(
          () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
        );
        if (overflow > 1) {
          failures++;
          console.log(`FAIL  ${label}: the page scrolls sideways by ${overflow}px`);
        }
        if (SHOTS) {
          const file = `${name}-${size}-${mode}`.replace(/[^a-z0-9]+/gi, "-");
          await page.screenshot({ path: `${SHOTS}/${file}.png`, fullPage: true });
        }
        for (const text of blocked) {
          failures++;
          console.log(`FAIL  ${label}: blocked by the Content-Security-Policy: ${text}`);
        }
        if (violations.length === 0 && blocked.length === 0 && overflow <= 1) {
          console.log(`ok    ${label}`);
        }
        for (const v of violations) {
          failures++;
          console.log(`FAIL  ${label}: ${v.id} [${v.impact}] ${v.help}`);
          for (const n of v.nodes.slice(0, 5)) console.log(`        ${n}`);
        }
        await page.close();
      }
    }
  }
} finally {
  await browser.close();
  server.kill();
}
process.exit(failures ? 1 : 0);
