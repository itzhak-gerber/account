import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../../app/App";
import { fixtureBody } from "../../test/apiFixtures";

const SCAN = {
  file_id: "f9",
  read: true,
  ai_enabled: true,
  supplier_id: "s1",
  supplier_name: "סיטונאות הצפון בע״מ",
  supplier_tax_id: "515555555",
  invoice_number: "A-7731",
  invoice_date: "2026-10-06",
  net_amount: "1000.00",
  vat_amount: "180.00",
  total: "1180.00",
};

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe("photographed supplier invoices", () => {
  it("fills the invoice from the photo and keeps the file with it", async () => {
    const posts: { url: string; body: unknown }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const reply = (body: unknown, status = 200) =>
          new Response(JSON.stringify(body), {
            status,
            headers: { "Content-Type": "application/json" },
          });
        if (url.endsWith("/scan")) return reply(SCAN, 201);
        if (init?.method === "POST") {
          posts.push({ url, body: JSON.parse(String(init.body)) });
          return reply({}, 201);
        }
        return reply(fixtureBody(url));
      }),
    );
    const { container } = render(
      <MemoryRouter initialEntries={["/purchasing?tab=invoices"]}>
        <App />
      </MemoryRouter>,
    );
    const user = userEvent.setup();

    await screen.findByRole("button", { name: "צילום חשבונית" });
    const camera = container.querySelector<HTMLInputElement>("input[capture]")!;
    await user.upload(camera, new File(["jpeg"], "invoice.jpg", { type: "image/jpeg" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/המערכת קראה את החשבונית/)).toBeInTheDocument();
    expect(within(dialog).getByLabelText(/מספר חשבונית/)).toHaveValue("A-7731");
    expect(within(dialog).getByLabelText(/לפני מע״מ/)).toHaveValue("1000");
    expect(within(dialog).getByLabelText(/^מע״מ/)).toHaveValue("180");
    const result = await axe.run(dialog, { rules: { "color-contrast": { enabled: false } } });
    expect(result.violations.map((v) => v.id)).toEqual([]);

    await user.click(within(dialog).getByRole("button", { name: "שמירה" }));
    await vi.waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0].body).toMatchObject({
      supplier_id: "s1",
      invoice_number: "A-7731",
      invoice_date: "2026-10-06",
      net_amount: "1000",
      vat_amount: "180",
      file_id: "f9",
    });
  }, 20000);
});
