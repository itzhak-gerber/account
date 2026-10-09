import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../../app/App";
import { fixtureBody } from "../../test/apiFixtures";

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe("allocation numbers", () => {
  it("offers to issue without the number when the tax authority is down", async () => {
    const draft = { ...(fixtureBody("/documents/d1") as object), status: "draft", number: null };
    const issues: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/issue")) {
          issues.push(url);
          return url.includes("without_allocation=true")
            ? json({ ...draft, status: "issued", number: 2, allocation_status: "pending" })
            : json({ error: { code: "allocation_failed", message: "No allocation number" } }, 409);
        }
        if (url.endsWith("/documents/d1")) return json(draft);
        return json(fixtureBody(url));
      }),
    );
    render(
      <MemoryRouter initialEntries={["/documents/d1"]}>
        <App />
      </MemoryRouter>,
    );
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "הפקת המסמך" }));
    const confirm = await screen.findByRole("dialog", { name: "להפיק את המסמך?" });
    await user.click(within(confirm).getByRole("button", { name: "הפקת המסמך" }));

    const problem = await screen.findByRole("dialog", { name: "לא התקבל מספר הקצאה" });
    expect(within(problem).getByText(/רשות המסים לא זמינה/)).toBeInTheDocument();
    await user.click(within(problem).getByRole("button", { name: "הפקה בלי מספר הקצאה" }));

    await vi.waitFor(() => expect(issues).toHaveLength(2));
    expect(issues[0]).not.toContain("without_allocation");
    expect(issues[1]).toContain("without_allocation=true");
  }, 20000);
});
