// Accessibility (IS 5568 / WCAG 2.0 AA): every screen is rendered with realistic data and
// checked with axe. Colour contrast is checked in the browser (jsdom has no layout or styles).
import { render, screen } from "@testing-library/react";
import axe from "axe-core";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./app/App";
import { fixtureBody, ME } from "./test/apiFixtures";

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

async function check(path: string, me: unknown = ME) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => json(fixtureBody(String(input), me))),
  );
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
  await screen.findByRole("heading", { level: 1 });
  // Let queries that started with the page settle (tables, counts).
  await new Promise((r) => setTimeout(r, 300));
  const result = await axe.run(document.body, {
    rules: { "color-contrast": { enabled: false } },
  });
  const problems = result.violations.map(
    (v) =>
      `${v.id} (${v.impact}): ${v.help}\n  ${v.nodes.map((n) => n.html.slice(0, 300)).join("\n  ")}`,
  );
  expect(problems, problems.join("\n")).toEqual([]);
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe("accessibility (axe)", () => {
  it.each([
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
  ])("%s", async (_name, path) => check(path), 20000);

  it("onboarding", () => check("/", { ...ME, memberships: [] }), 20000);
  it("two-factor required", () => check("/", { ...ME, memberships: [], mfa: false }), 20000);
});
