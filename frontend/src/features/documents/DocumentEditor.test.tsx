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
  has_logo: false,
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
  {
    type: "receipt",
    title: "קבלה",
    has_lines: false,
    has_payments: true,
    is_tax_document: false,
    shows_vat: false,
    has_due_date: false,
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
    payment_status: "unpaid",
    amount_paid: "0.00",
    amount_credited: "0.00",
    balance_due: "1180.00",
    allocations: [],
    deliveries: [],
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

const NO_STOCK = { items: [], kits: [], total_value: "0.00" };

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
        if (url.endsWith("/inventory")) return json(NO_STOCK);
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
    // Types a whole invoice key by key: about 3s locally, more on CI runners.
  }, 20000);

  it("starts a receipt from an unpaid invoice with its balance pre-filled", async () => {
    const calls: { method: string; url: string; body: unknown }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        calls.push({ method, url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
        if (url === "/api/v1/me") return json(ME);
        if (url.endsWith("/document-types")) return json(TYPES);
        if (url.endsWith("/documents/inv1")) return json({ ...issuedDoc("inv1"), number: 7 });
        if (method === "POST" && url.endsWith("/documents"))
          return json({ ...issuedDoc("r1"), type: "receipt", status: "draft", number: null }, 201);
        return json([]);
      }),
    );
    render(
      <MemoryRouter initialEntries={["/documents/new?type=receipt&invoice=inv1"]}>
        <App />
      </MemoryRouter>,
    );
    const user = userEvent.setup();

    expect(await screen.findByText(/חשבונית מס מס׳ 7/)).toBeInTheDocument();
    expect(screen.getByLabelText("סכום לחשבונית זו")).toHaveValue("1180.00");
    await user.clear(screen.getByLabelText("סכום לחשבונית זו"));
    await user.type(screen.getByLabelText("סכום לחשבונית זו"), "500");
    await user.click(screen.getByRole("button", { name: "שמירת טיוטה" }));

    const post = calls.find((c) => c.method === "POST");
    expect(post?.body).toMatchObject({
      type: "receipt",
      customer: { name: "לקוח" },
      allocations: [{ invoice_id: "inv1", amount: "500" }],
      payments: [{ method: "bank_transfer", amount: "1180.00" }],
    });
  });

  it("emails an issued document with the default recipient plus a typed one", async () => {
    const calls: { method: string; url: string; body: unknown }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        calls.push({ method, url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
        if (url === "/api/v1/me") return json(ME);
        if (url.endsWith("/document-types")) return json(TYPES);
        if (url.endsWith("/email-defaults"))
          return json({
            to: ["billing@client.example"],
            subject: "חשבונית מס מס׳ 1",
            message: "שלום",
          });
        if (method === "POST" && url.endsWith("/send-email"))
          return json(
            {
              id: "e1",
              recipients: [],
              subject: "",
              variant: "original",
              status: "queued",
              error: null,
              sent_at: null,
              created_at: "",
            },
            202,
          );
        if (url.endsWith("/documents/d1")) return json(issuedDoc("d1"));
        return json([]);
      }),
    );
    render(
      <MemoryRouter initialEntries={["/documents/d1"]}>
        <App />
      </MemoryRouter>,
    );
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "שליחה במייל" }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("billing@client.example")).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText(/נמענים/), "boss@client.example");
    await user.click(within(dialog).getByRole("button", { name: "שליחה" }));

    await vi.waitFor(() => expect(calls.some((c) => c.url.endsWith("/send-email"))).toBe(true));
    const post = calls.find((c) => c.url.endsWith("/send-email"));
    expect(post?.body).toEqual({
      to: ["billing@client.example", "boss@client.example"],
      subject: "חשבונית מס מס׳ 1",
      message: "שלום",
    });
  });

  it("warns before the first PDF download uses up the original", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === "/api/v1/me") return json(ME);
        if (url.endsWith("/document-types")) return json(TYPES);
        if (url.endsWith("/email-defaults"))
          return json({ to: [], subject: "חשבונית מס מס׳ 1", message: "" });
        if (url.endsWith("/documents/d1")) return json(issuedDoc("d1"));
        return json([]);
      }),
    );
    const open = vi.fn();
    vi.stubGlobal("open", open);
    render(
      <MemoryRouter initialEntries={["/documents/d1"]}>
        <App />
      </MemoryRouter>,
    );
    const user = userEvent.setup();

    await user.click(await screen.findByRole("link", { name: "הורדת PDF" }));
    let dialog = await screen.findByRole("dialog", { name: "הורדת המקור של המסמך" });
    await user.click(within(dialog).getByRole("button", { name: "ביטול" }));
    expect(open).not.toHaveBeenCalled();

    await user.click(await screen.findByRole("link", { name: "הורדת PDF" }));
    dialog = await screen.findByRole("dialog", { name: "הורדת המקור של המסמך" });
    await user.click(within(dialog).getByRole("button", { name: "הורדת המקור" }));
    expect(open).toHaveBeenCalledWith(
      expect.stringContaining("/documents/d1/pdf"),
      "_blank",
      "noopener",
    );

    await user.click(await screen.findByRole("link", { name: "הורדת PDF" }));
    dialog = await screen.findByRole("dialog", { name: "הורדת המקור של המסמך" });
    await user.click(within(dialog).getByRole("button", { name: "שליחת המקור ללקוח במייל" }));
    expect(await screen.findByRole("button", { name: "שליחה" })).toBeInTheDocument();
  });
});
