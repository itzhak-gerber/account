import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../../app/App";

const BUSINESS = {
  id: "b1",
  legal_name: "דוגמה בע״מ",
  display_name: "דוגמה",
  tax_id: "516179157",
  business_type: "company",
  address_street: "הרצל 1",
  address_city: "תל אביב",
  address_zip: "",
  phone: "",
  email: "",
  default_currency: "ILS",
};
const ME = {
  user: { id: "u1", email: "owner@example.com", full_name: "ישראל" },
  memberships: [{ business: BUSINESS, role: "owner" }],
  mfa: true,
  csrf_token: "csrf",
};
const TYPES = [
  {
    type: "tax_invoice",
    title: "חשבונית מס",
    has_lines: true,
    has_payments: false,
    is_tax_document: true,
    shows_vat: true,
    has_due_date: true,
  },
];

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function issuedDoc(id: string) {
  return {
    id,
    type: "tax_invoice",
    title: "חשבונית מס",
    status: "issued",
    number: 1,
    issue_date: "2026-10-05",
    due_date: null,
    customer_id: null,
    customer: {
      name: "לקוח",
      tax_id: "",
      email: null,
      phone: "",
      address_street: "",
      address_city: "",
      address_zip: "",
    },
    currency: "ILS",
    prices_include_vat: false,
    vat_rate: "0.1800",
    subtotal: "1000.00",
    discount_total: "0.00",
    vat_amount: "180.00",
    total: "1180.00",
    notes: "",
    allocation_number: null,
    lines: [],
    payments: [],
    related: [],
    original_delivered_at: null,
    issued_at: "2026-10-05T10:00:00Z",
    created_at: "2026-10-05T10:00:00Z",
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe("DocumentEditor", () => {
  it("shows live VAT totals and issues after confirmation", async () => {
    const calls: { method: string; url: string; body: unknown }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        calls.push({ method, url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
        if (url === "/api/v1/me") return json(ME);
        if (url.endsWith("/document-types")) return json(TYPES);
        if (url.includes("/customers") || url.includes("/items")) return json([]);
        if (method === "POST" && url.endsWith("/documents"))
          return json({ ...issuedDoc("d1"), status: "draft", number: null }, 201);
        if (method === "POST" && url.endsWith("/d1/issue")) return json(issuedDoc("d1"));
        if (url.endsWith("/documents/d1")) return json(issuedDoc("d1"));
        return json([]);
      }),
    );
    render(
      <MemoryRouter initialEntries={["/documents/new?type=tax_invoice"]}>
        <App />
      </MemoryRouter>,
    );
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText("לקוח"), "לקוח");
    await user.type(screen.getByLabelText("תיאור"), "ייעוץ");
    const price = screen.getByLabelText("מחיר");
    await user.type(price, "1000");

    const totals = screen.getByText("סה״כ לפני מע״מ").closest("div")!.parentElement!;
    const amounts = within(totals)
      .getAllByText(/\d\.\d\d/)
      .map((el) => el.textContent!.replace(/[^\d.,]/g, ""));
    expect(amounts).toEqual(["1,000.00", "180.00", "1,180.00"]);

    await user.click(screen.getByRole("button", { name: "הפקת המסמך" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/לא ניתן יהיה לשנות או למחוק/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "הפקת המסמך" }));

    expect(await screen.findByRole("heading", { name: /חשבונית מס מס׳ 1/ })).toBeInTheDocument();
    const writes = calls.filter((c) => c.method !== "GET");
    expect(writes.map((c) => `${c.method} ${c.url}`)).toEqual([
      "POST /api/v1/businesses/b1/documents",
      "POST /api/v1/businesses/b1/documents/d1/issue",
    ]);
    expect(writes[0].body).toMatchObject({
      type: "tax_invoice",
      customer: { name: "לקוח" },
      lines: [{ description: "ייעוץ", quantity: "1", unit_price: "1000" }],
    });
  });
});
