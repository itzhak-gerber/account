import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Me, User } from "../../api/types";
import { App } from "../../app/App";

const USER: User = {
  id: "u1",
  email: "owner@example.com",
  full_name: "ישראל ישראלי",
  theme: "system",
  text_size: "device",
};

function me(user: Partial<User> = {}): Me {
  return {
    user: { ...USER, ...user },
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
      },
    ],
    mfa: true,
    csrf_token: "csrf",
  };
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mockApi(user: Partial<User> = {}, saveStatus = 200) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.startsWith("/api/v1/me/display-preferences")) {
      const change = JSON.parse(String(init?.body)) as Partial<User>;
      return saveStatus === 200
        ? json({ ...USER, ...user, ...change })
        : json({ error: { code: "unknown_error" } }, saveStatus);
    }
    if (url === "/api/v1/me") return json(me(user));
    return json([], 200);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderProfile() {
  return render(
    <MemoryRouter initialEntries={["/profile"]}>
      <App />
    </MemoryRouter>,
  );
}

const themeGroup = async () =>
  within(await screen.findByRole("radiogroup", { name: "ערכת צבעים" }));
const sizeGroup = async () => within(await screen.findByRole("radiogroup", { name: "גודל טקסט" }));
const statusBar = () => document.querySelector('meta[name="theme-color"]')?.getAttribute("content");
const rootFontSize = () => getComputedStyle(document.documentElement).fontSize;

beforeEach(() => {
  const meta = document.createElement("meta");
  meta.name = "theme-color";
  document.head.append(meta);
});

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
  document.querySelector('meta[name="theme-color"]')?.remove();
});

describe("Display preferences", () => {
  it("switches to dark and back, saving to the profile", async () => {
    const fetchMock = mockApi();
    renderProfile();
    const user = userEvent.setup();

    expect((await themeGroup()).getByRole("radio", { name: "לפי המכשיר" })).toBeChecked();
    expect(statusBar()).toBe("#1e4fd8");

    await user.click(screen.getByRole("radio", { name: "כהה" }));
    await waitFor(() => expect(statusBar()).toBe("#1c1f24"));
    const saved = fetchMock.mock.calls.find(([url]) =>
      String(url).endsWith("/me/display-preferences"),
    );
    expect(saved?.[1]?.method).toBe("PATCH");
    expect(JSON.parse(String(saved?.[1]?.body))).toEqual({ theme: "dark" });
    expect(new Headers(saved?.[1]?.headers).get("X-CSRF-Token")).toBe("csrf");

    await user.click(screen.getByRole("radio", { name: "בהירה" }));
    await waitFor(() => expect(statusBar()).toBe("#1e4fd8"));
  });

  it("uses the saved theme and text size on load, and remembers them in this browser", async () => {
    mockApi({ theme: "dark", text_size: "xlarge" });
    renderProfile();

    expect(await screen.findByRole("radio", { name: "כהה", checked: true })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "גדול מאוד", checked: true })).toBeInTheDocument();
    await waitFor(() => expect(statusBar()).toBe("#1c1f24"));
    expect(rootFontSize()).toBe("125%");
    expect(JSON.parse(localStorage.getItem("display-preferences") ?? "{}")).toEqual({
      theme: "dark",
      text_size: "xlarge",
    });
  });

  it("changes the text size at once", async () => {
    mockApi();
    renderProfile();
    const user = userEvent.setup();

    await user.click(await screen.findByRole("radio", { name: "גדול" }));
    await waitFor(() => expect(rootFontSize()).toBe("112.5%"));
    await user.click((await sizeGroup()).getByRole("radio", { name: "לפי המכשיר" }));
    await waitFor(() => expect(rootFontSize()).not.toBe("112.5%"));
  });

  it("puts the choice back when saving fails", async () => {
    mockApi({}, 500);
    renderProfile();
    const user = userEvent.setup();

    await user.click(await screen.findByRole("radio", { name: "כהה" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect((await themeGroup()).getByRole("radio", { name: "לפי המכשיר" })).toBeChecked();
    expect(statusBar()).toBe("#1e4fd8");
  });
});
