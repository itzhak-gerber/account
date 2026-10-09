import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../../app/App";
import { fixtureBody } from "../../test/apiFixtures";

type Call = { method: string; url: string; body: unknown };

function stubApi(): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      calls.push({ method, url, body });
      const result = method === "GET" ? fixtureBody(url) : { id: "new", ...body };
      return new Response(JSON.stringify(result), {
        status: method === "POST" ? 201 : 200,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
  return calls;
}

async function noAxeProblems(node: Element) {
  const result = await axe.run(node, { rules: { "color-contrast": { enabled: false } } });
  const problems = result.violations.map((v) => `${v.id}: ${v.help}`);
  expect(problems, problems.join("\n")).toEqual([]);
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe("purchasing", () => {
  it("receives what is still due on an order, at the order's cost", async () => {
    const calls = stubApi();
    render(
      <MemoryRouter initialEntries={["/purchasing"]}>
        <App />
      </MemoryRouter>,
    );
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "הזמנה 1" }));
    const view = await screen.findByRole("dialog");
    expect(within(view).getByText("הובלה")).toBeInTheDocument();
    await noAxeProblems(view);
    await user.click(within(view).getByRole("button", { name: "קליטת סחורה" }));

    const receipt = await screen.findByRole("dialog", { name: "קליטת סחורה מהזמנה 1" });
    // 30 ordered, 10 already arrived; the freight line is not goods.
    expect(await within(receipt).findByLabelText("כמות (שורה 1)")).toHaveValue("20");
    expect(within(receipt).queryByLabelText("כמות (שורה 2)")).toBeNull();
    await noAxeProblems(receipt);
    await user.type(within(receipt).getByLabelText("מספר תעודת משלוח של הספק"), "5530");
    await user.click(within(receipt).getByRole("button", { name: "קליטה למלאי" }));

    await vi.waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    const post = calls.find((c) => c.method === "POST")!;
    expect(post.url).toBe("/api/v1/businesses/b1/goods-receipts");
    expect(post.body).toMatchObject({
      supplier_id: "s1",
      purchase_order_id: "po1",
      supplier_reference: "5530",
      lines: [{ item_id: "i2", order_line_id: "pol1", quantity: "20", unit_cost: "30" }],
    });
  }, 20000);

  it("fills in VAT from the net amount of a supplier invoice", async () => {
    const calls = stubApi();
    render(
      <MemoryRouter initialEntries={["/purchasing?tab=invoices"]}>
        <App />
      </MemoryRouter>,
    );
    const user = userEvent.setup();

    // The open balance counts the unpaid invoice only; it is past its due date.
    await screen.findByRole("button", { name: "A-1001" });
    const balance = screen.getByText("יתרה לתשלום לספקים");
    expect(balance.nextSibling).toHaveTextContent(/354\.00/);
    await user.click(await screen.findByRole("button", { name: "חשבונית ספק חדשה" }));
    const dialog = await screen.findByRole("dialog");
    await noAxeProblems(dialog);
    await user.click(within(dialog).getByLabelText(/ספק/, { selector: "input" }));
    await user.click(await screen.findByRole("option", { name: "סיטונאות הצפון בע״מ" }));
    await user.type(within(dialog).getByLabelText(/מספר חשבונית/), "B-7");
    await user.type(within(dialog).getByLabelText(/לפני מע״מ/), "1000");
    expect(within(dialog).getByLabelText(/^מע״מ/)).toHaveValue("180.00");
    await user.click(within(dialog).getByRole("button", { name: "שמירה" }));

    await vi.waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    expect(calls.find((c) => c.method === "POST")!.body).toMatchObject({
      supplier_id: "s1",
      invoice_number: "B-7",
      net_amount: "1000",
      vat_amount: "180.00",
      paid_date: null,
    });
  }, 20000);
});
