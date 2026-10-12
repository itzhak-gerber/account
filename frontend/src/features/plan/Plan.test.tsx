import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Me, Plan, PlanStatus, PlanSummary } from "../../api/types";
import { App } from "../../app/App";

const PLAN: Plan = {
  id: "p1",
  name: "עסקי",
  description: "מסמכים ומלאי",
  modules: ["inventory"],
  duration_months: 12,
  price: "1200.00",
  current_price: "1230.00",
  linkage: "cpi",
  base_index: "100.0000",
  documents_per_month: 10,
  document_overage_price: "3.00",
  scans_per_month: null,
  scan_overage_price: null,
  is_active: true,
};

const STATUS: PlanStatus = {
  read_only: false,
  kind: "trial",
  name: "ניסיון",
  modules: [],
  starts_on: "2026-10-01",
  ends_on: "2026-10-31",
  document_overage_price: "3.00",
  scan_overage_price: null,
  documents: { used: 12, quota: 10, over: 2, over_amount: "6.00" },
  scans: { used: 0, quota: null, over: 0, over_amount: "0.00" },
  available_plans: [PLAN],
};

function me(plan: PlanSummary, extra: Partial<Me> = {}): Me {
  return {
    user: {
      id: "u1",
      email: "owner@example.com",
      full_name: "ישראל ישראלי",
      theme: "system",
      text_size: "device",
    },
    memberships: [
      {
        business: {
          id: "b1",
          legal_name: "דוגמה בע״מ",
          display_name: "דוגמה",
          tax_id: "516179157",
          business_type: "company",
          address_street: "",
          address_city: "",
          address_zip: "",
          phone: "",
          email: "",
          default_currency: "ILS",
          has_logo: false,
        },
        role: "owner",
        plan,
      },
    ],
    mfa: true,
    csrf_token: "csrf",
    ...extra,
  };
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mockApi(routes: Record<string, unknown>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
    const url = String(input).split("?")[0];
    if (url in routes) return json(routes[url]);
    if (url.endsWith("/upgrade-request")) return json({ status: "sent" }, 202);
    if (url.endsWith("/inventory")) return json({ items: [], kits: [], total_value: "0" });
    return json([]);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

const BASIC: PlanSummary = { read_only: false, modules: [], ends_on: "2026-10-31" };

describe("Plans in the app", () => {
  it("offers the inventory module where it would be, and sends an upgrade request", async () => {
    const fetchMock = mockApi({
      "/api/v1/me": me(BASIC),
      "/api/v1/businesses/b1/plan": STATUS,
    });
    renderAt("/inventory");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "פתיחת תפריט" }));
    const nav = await screen.findByRole("link", { name: /מלאי/ });
    expect(within(nav).getByText("שדרוג")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(
      await screen.findByText("ניהול מלאי – לא כלול בתוכנית", { selector: "div" }),
    ).toBeInTheDocument();

    await user.click(await screen.findByRole("button", { name: "לפרטים ולשדרוג" }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("עסקי")).toBeInTheDocument();
    expect(within(dialog).getByText(/1,230\.00/)).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText("הודעה (לא חובה)"), "בבקשה");
    await user.click(within(dialog).getByRole("button", { name: "בקשת שדרוג" }));
    expect(await within(dialog).findByText("הבקשה נשלחה. ניצור קשר בהקדם.")).toBeInTheDocument();
    const sent = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/upgrade-request"));
    expect(JSON.parse(String(sent?.[1]?.body))).toEqual({
      module: "inventory",
      plan_id: null,
      message: "בבקשה",
    });
  });

  it("warns when the business is read-only", async () => {
    mockApi({
      "/api/v1/me": me({ read_only: true, modules: [], ends_on: null }),
      "/api/v1/businesses/b1/plan": { ...STATUS, read_only: true, kind: null, name: null },
    });
    renderAt("/documents");

    expect(await screen.findByText(/התוכנית של העסק הסתיימה/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "לתוכנית שלי" })).toHaveAttribute(
      "href",
      "/settings?tab=plan",
    );
  });

  it("shows the plan, this month's usage and the plans on offer", async () => {
    mockApi({
      "/api/v1/me": me(BASIC),
      "/api/v1/businesses/b1/plan": STATUS,
    });
    renderAt("/settings?tab=plan");

    expect(await screen.findByText("ניסיון")).toBeInTheDocument();
    expect(screen.getByText("תקופת ניסיון")).toBeInTheDocument();
    expect(screen.getByText("12 מתוך 10")).toBeInTheDocument();
    expect(screen.getByText(/מעבר למכסה: 2, חיוב/)).toBeInTheDocument();
    expect(screen.getByText("ניהול מלאי – לא כלול")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "בקשה לתוכנית הזו" })).toBeInTheDocument();
  });

  it("replaces scanning with an upgrade button when the plan lacks it", async () => {
    mockApi({
      "/api/v1/me": me({ read_only: false, modules: ["inventory"], ends_on: null }),
      "/api/v1/businesses/b1/plan": STATUS,
    });
    renderAt("/purchasing?tab=invoices");

    expect(
      await screen.findByRole("button", { name: "צילום חשבונית – שדרוג" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "העלאת קובץ" })).not.toBeInTheDocument();
  });
});

describe("Operator screen", () => {
  it("is linked for operators and creates a plan", async () => {
    const fetchMock = mockApi({
      "/api/v1/me": me(BASIC, { is_operator: true }),
      "/api/v1/admin/plans": [PLAN],
      "/api/v1/admin/businesses": [
        {
          id: "b1",
          display_name: "דוגמה",
          legal_name: "דוגמה בע״מ",
          tax_id: "516179157",
          created_at: "2026-10-01T10:00:00Z",
          owner_email: "owner@example.com",
          subscription_id: "s1",
          kind: "trial",
          plan_name: "ניסיון",
          ends_on: "2026-10-31",
          documents_this_month: 12,
          scans_this_month: 0,
        },
      ],
    });
    renderAt("/admin");
    const user = userEvent.setup();

    expect(await screen.findByRole("cell", { name: "owner@example.com" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "פתיחת תפריט" }));
    expect(await screen.findByRole("link", { name: "ניהול המערכת" })).toBeInTheDocument();
    await user.keyboard("{Escape}");

    await user.click(await screen.findByRole("tab", { name: "תוכניות" }));
    await user.click(await screen.findByRole("button", { name: "תוכנית חדשה" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText(/^שם/), "פרימיום");
    await user.click(within(dialog).getByLabelText("סריקת חשבוניות ספקים"));
    await user.type(within(dialog).getByLabelText(/מחיר לכל התקופה/), "2400");
    await user.type(within(dialog).getByLabelText(/סריקות בחודש/), "50");
    await user.click(within(dialog).getByRole("button", { name: "שמירה" }));

    const saved = fetchMock.mock.calls.find(
      ([url, init]) => String(url).endsWith("/admin/plans") && init?.method === "POST",
    );
    expect(JSON.parse(String(saved?.[1]?.body))).toMatchObject({
      name: "פרימיום",
      modules: ["scanning"],
      duration_months: 12,
      price: "2400",
      scans_per_month: 50,
      documents_per_month: null,
      linkage: "none",
    });
  });

  it("is not linked for other users", async () => {
    mockApi({ "/api/v1/me": me(BASIC) });
    renderAt("/documents");
    await userEvent.setup().click(await screen.findByRole("button", { name: "פתיחת תפריט" }));
    await screen.findByRole("link", { name: /מלאי/ });
    expect(screen.queryByRole("link", { name: "ניהול המערכת" })).not.toBeInTheDocument();
  });
});
