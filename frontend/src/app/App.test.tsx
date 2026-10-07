import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Me, Member } from "../api/types";
import { App } from "./App";

const BUSINESS = {
  id: "b1",
  legal_name: "דוגמה בע״מ",
  display_name: "דוגמה",
  tax_id: "516179157",
  business_type: "company" as const,
  address_street: "",
  address_city: "תל אביב",
  address_zip: "",
  phone: "",
  email: "",
  default_currency: "ILS",
  has_logo: false,
};

function me(overrides: Partial<Me> = {}): Me {
  return {
    user: { id: "u1", email: "owner@example.com", full_name: "ישראל ישראלי" },
    memberships: [{ business: BUSINESS, role: "owner" }],
    mfa: true,
    csrf_token: "csrf",
    ...overrides,
  };
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mockApi(routes: Record<string, (method: string) => Response>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const match = Object.keys(routes).find((path) => url.startsWith(path));
    return match
      ? routes[match](init?.method ?? "GET")
      : json({ error: { code: "not_found" } }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const HEALTH = () => json({ status: "ok", version: "0.1.0", environment: "test", database: "ok" });

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

describe("App", () => {
  it("shows the landing page with login and sign-up when signed out", async () => {
    mockApi({ "/api/v1/me": () => json({ error: { code: "not_authenticated" } }, 401) });

    renderAt("/");

    expect(await screen.findByRole("button", { name: "התחברות" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "הרשמה" })).toBeInTheDocument();
  });

  it("asks for two-factor setup before creating a first business", async () => {
    mockApi({ "/api/v1/me": () => json(me({ memberships: [], mfa: false })) });

    renderAt("/");

    expect(await screen.findByRole("heading", { name: "נדרש אימות דו-שלבי" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "הפעלת אימות דו-שלבי" })).toBeInTheDocument();
  });

  it("shows the business creation form once two-factor is on", async () => {
    mockApi({ "/api/v1/me": () => json(me({ memberships: [] })) });

    renderAt("/");

    expect(await screen.findByRole("heading", { name: "יצירת העסק שלכם" })).toBeInTheDocument();
    expect(screen.getByLabelText(/מספר עוסק/)).toBeInTheDocument();
  });

  it("validates the tax ID check digit before submitting", async () => {
    const fetchMock = mockApi({ "/api/v1/me": () => json(me({ memberships: [] })) });
    renderAt("/");
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText(/שם העסק/), "עסק");
    await user.type(screen.getByLabelText(/מספר עוסק/), "123456789");
    await user.click(screen.getByRole("button", { name: "יצירת העסק" }));

    expect(screen.getByText("מספר לא תקין (נבדקת ספרת ביקורת)")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
  });

  it("renders the dashboard for the current business", async () => {
    mockApi({ "/api/v1/me": () => json(me()), "/api/v1/health": HEALTH });

    renderAt("/");

    expect(await screen.findByText(/דוגמה · התפקיד שלך: בעלים/)).toBeInTheDocument();
    expect(await screen.findByText("0.1.0")).toBeInTheDocument();
  });

  it("blocks owners who signed in without two-factor", async () => {
    mockApi({ "/api/v1/me": () => json(me({ mfa: false })), "/api/v1/health": HEALTH });

    renderAt("/");

    expect(await screen.findByRole("heading", { name: "נדרש אימות דו-שלבי" })).toBeInTheDocument();
    expect(screen.queryByText(/התפקיד שלך/)).not.toBeInTheDocument();
  });

  it("lists team members in settings and sends CSRF on invites", async () => {
    const members: Member[] = [
      {
        id: "m1",
        user_id: "u1",
        email: "owner@example.com",
        full_name: "ישראל ישראלי",
        role: "owner",
        joined_at: "2026-10-04T00:00:00Z",
      },
    ];
    const fetchMock = mockApi({
      "/api/v1/me": () => json(me()),
      "/api/v1/businesses/b1/members": () => json(members),
      "/api/v1/businesses/b1/invitations": (method) =>
        method === "POST"
          ? json({
              id: "i1",
              email: "dana@example.com",
              role: "member",
              expires_at: "",
              created_at: "",
            })
          : json([]),
    });
    renderAt("/settings");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("tab", { name: "משתמשים" }));
    const list = await screen.findByText(/ישראל ישראלי \(את\/ה\)/);
    expect(within(list.closest("li")!).getByText("owner@example.com")).toBeInTheDocument();

    await user.type(screen.getByLabelText(/^דוא״ל/), "dana@example.com");
    await user.click(screen.getByRole("button", { name: "שליחת הזמנה" }));

    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(post).toBeDefined();
    const [url, init] = post!;
    expect(url).toBe("/api/v1/businesses/b1/invitations");
    expect((init!.headers as Record<string, string>)["X-CSRF-Token"]).toBe("csrf");
  });

  it("shows this month's figures and the 12-month chart on the dashboard", async () => {
    mockApi({
      "/api/v1/me": () => json(me()),
      "/api/v1/health": HEALTH,
      "/api/v1/businesses/b1/reports/dashboard": () =>
        json({
          vat_registered: true,
          month: "2026-10-01",
          income_net: "1090.00",
          income_vat: "196.20",
          received: "0.00",
          open_balance: "2286.20",
          open_documents: 2,
          overdue_balance: "1000.00",
          overdue_documents: 1,
          income_by_month: Array.from({ length: 12 }, (_, i) => ({
            month: `2026-${String(i + 1).padStart(2, "0")}-01`,
            amount: i === 9 ? "1090.00" : "0.00",
          })),
        }),
    });

    renderAt("/");

    expect(await screen.findByText("הכנסות לפני מע״מ · החודש")).toBeInTheDocument();
    expect(screen.getByText(/מתוכם באיחור: .*1,000\.00/)).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "הכנסות לפני מע״מ – 12 החודשים האחרונים" });
    expect(within(table).getAllByRole("row")).toHaveLength(12);
  });

  it("shows the income report with VAT split and an Excel link for the chosen period", async () => {
    const fetchMock = mockApi({
      "/api/v1/me": () => json(me()),
      "/api/v1/businesses/b1/reports/income": () =>
        json({
          date_from: "2026-10-01",
          date_to: "2026-10-07",
          totals: {
            documents: 1,
            taxable: "1000.00",
            zero_rated: "200.00",
            exempt: "300.00",
            net: "1500.00",
            vat: "180.00",
            total: "1680.00",
          },
          months: [],
          documents: [
            {
              id: "d1",
              type: "tax_invoice",
              number: 7,
              issue_date: "2026-10-05",
              customer_name: "לקוח בע״מ",
              customer_tax_id: "",
              taxable: "1000.00",
              zero_rated: "200.00",
              exempt: "300.00",
              net: "1500.00",
              vat: "180.00",
              total: "1680.00",
            },
          ],
        }),
    });

    renderAt("/reports");

    const documents = await screen.findByRole("table", { name: "המסמכים" });
    expect(within(documents).getByText("חשבונית מס 7")).toBeInTheDocument();
    expect(screen.getAllByText(/500\.00/).length).toBeGreaterThan(0); // zero-rated + exempt
    const url = String(fetchMock.mock.calls.find(([u]) => String(u).includes("/reports/"))![0]);
    expect(url).toMatch(/date_from=\d{4}-\d{2}-01&date_to=/);
    expect(screen.getByRole("link", { name: "הורדה לאקסל" })).toHaveAttribute(
      "href",
      expect.stringMatching(/\/reports\/income\.xlsx\?date_from=/),
    );
  });

  it("shows unread notifications under the bell and marks one read when opened", async () => {
    const fetchMock = mockApi({
      "/api/v1/me": () => json(me()),
      "/api/v1/health": HEALTH,
      "/api/v1/businesses/b1/notifications/unread-count": () => json({ unread: 3 }),
      "/api/v1/businesses/b1/notifications/read": () => json({ unread: 2 }),
      "/api/v1/businesses/b1/notifications": () =>
        json([
          {
            id: "n1",
            event: "payment_received",
            title: "התקבל תשלום",
            body: "קבלה מס׳ 4 מבטא שיווק: ₪5,000.00",
            link: "/documents/d4",
            read_at: null,
            created_at: new Date().toISOString(),
          },
        ]),
    });
    renderAt("/");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "התראות, 3 חדשות" }));
    expect(await screen.findByText("קבלה מס׳ 4 מבטא שיווק: ₪5,000.00")).toBeInTheDocument();
    expect(screen.getByText("עכשיו")).toBeInTheDocument();
    await user.click(screen.getByText("התקבל תשלום"));

    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(post![0]).toBe("/api/v1/businesses/b1/notifications/read");
    expect(JSON.parse(String(post![1]!.body))).toEqual({ ids: ["n1"] });
  });

  it("saves a notification channel choice from the profile page", async () => {
    const prefs = [
      { event: "payment_received", channels: { in_app: true, email: false } },
      { event: "invoice_overdue", channels: { in_app: true, email: true } },
    ];
    const fetchMock = mockApi({
      "/api/v1/me/notification-preferences": () => json(prefs),
      "/api/v1/me/devices": () =>
        json([
          {
            id: "dev1",
            label: "Chrome · Windows",
            last_ip: "10.0.0.5",
            first_seen_at: "2026-10-01T08:00:00Z",
            last_seen_at: "2026-10-07T08:00:00Z",
            current: true,
          },
        ]),
      "/api/v1/me": () => json(me()),
    });
    renderAt("/profile");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("switch", { name: "התקבל תשלום: במייל" }));
    const devices = await screen.findByRole("list", { name: "מכשירים שנכנסו לחשבון" });
    expect(within(devices).getByText("Chrome · Windows")).toBeInTheDocument();
    expect(within(devices).getByText("המכשיר הזה")).toBeInTheDocument();

    const put = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT");
    expect(put![0]).toBe("/api/v1/me/notification-preferences");
    expect(JSON.parse(String(put![1]!.body))).toEqual({
      preferences: { payment_received: { in_app: true, email: true } },
    });
  });
});
