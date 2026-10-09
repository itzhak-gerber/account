import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../../app/App";
import { fixtureBody } from "../../test/apiFixtures";

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe("delivery notes", () => {
  it("bills the customer's open delivery notes in one invoice", async () => {
    const posts: { url: string; body: unknown }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (init?.method === "POST") {
          posts.push({ url, body: JSON.parse(String(init.body)) });
          return new Response(
            JSON.stringify({ ...(fixtureBody("/documents/d1") as object), id: "d9" }),
            {
              status: 201,
              headers: { "Content-Type": "application/json" },
            },
          );
        }
        return new Response(JSON.stringify(fixtureBody(url)), {
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
    render(
      <MemoryRouter initialEntries={["/documents"]}>
        <App />
      </MemoryRouter>,
    );
    const user = userEvent.setup();

    expect(await screen.findAllByText("טרם חויבה")).toHaveLength(2);
    await user.click(screen.getByRole("button", { name: "תעודות משלוח פתוחות" }));
    await user.click(await screen.findByRole("button", { name: "חשבונית מרכזת מתעודות משלוח" }));
    const dialog = await screen.findByRole("dialog", { name: "חשבונית מרכזת" });
    // Both notes of the customer are ticked; leave out the second one.
    await user.click(await within(dialog).findByLabelText(/תעודת משלוח 4/));
    const result = await axe.run(dialog, { rules: { "color-contrast": { enabled: false } } });
    expect(result.violations.map((v) => v.id)).toEqual([]);
    await user.click(within(dialog).getByRole("button", { name: "יצירת חשבונית מתעודה אחת" }));

    await vi.waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]).toEqual({
      url: "/api/v1/businesses/b1/documents/invoice-delivery-notes",
      body: { delivery_note_ids: ["dn3"], type: "tax_invoice" },
    });
  }, 20000);
});
