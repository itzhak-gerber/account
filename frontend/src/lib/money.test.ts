import { describe, expect, it } from "vitest";

import { formatDate, previewTotals } from "./money";

const line = (quantity: string, unit_price: string, discount_percent = "0") => ({
  quantity,
  unit_price,
  discount_percent,
  vat_type: "standard" as const,
});

describe("previewTotals (mirrors backend tests)", () => {
  it("adds VAT on top", () => {
    expect(previewTotals([line("2", "500"), line("1", "100", "10")], 0.18, false)).toEqual({
      lineTotals: [1000, 90],
      subtotal: 1090,
      vat: 196.2,
      total: 1286.2,
    });
  });

  it("extracts VAT from prices that include it", () => {
    const t = previewTotals([line("1", "118")], 0.18, true);
    expect([t.subtotal, t.vat, t.total]).toEqual([100, 18, 118]);
  });

  it("rounds half up", () => {
    const t = previewTotals([line("1.5", "9.99")], 0.17, false);
    expect([t.lineTotals[0], t.vat, t.total]).toEqual([14.99, 2.55, 17.54]);
  });

  it("formats dates the Israeli way", () => {
    expect(formatDate("2026-10-05")).toBe("05/10/2026");
  });
});
