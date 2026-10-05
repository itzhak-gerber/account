import type { LineInput, VatType } from "../api/types";

const shekel = new Intl.NumberFormat("he-IL", { style: "currency", currency: "ILS" });

export function formatMoney(value: string | number): string {
  return shekel.format(Number(value || 0));
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
}

/** Round half-up to agorot, working in integer agorot to avoid float drift. */
function toAgorot(value: number): number {
  return Math.sign(value) * Math.round(Math.abs(value) * 100 + 1e-9);
}

export interface PreviewTotals {
  lineTotals: number[];
  subtotal: number;
  vat: number;
  total: number;
}

/**
 * Live preview while editing. Mirrors the server rules (backend/app/services/calc.py);
 * the server recalculates and its numbers are the ones that count.
 */
export function previewTotals(
  lines: Pick<LineInput, "quantity" | "unit_price" | "discount_percent" | "vat_type">[],
  vatRate: number,
  pricesIncludeVat: boolean,
): PreviewTotals {
  const lineAgorot = lines.map((l) =>
    toAgorot(
      (Number(l.quantity || 0) *
        Number(l.unit_price || 0) *
        (100 - Number(l.discount_percent || 0))) /
        100,
    ),
  );
  const taxable = lineAgorot.reduce(
    (sum, a, i) => sum + ((lines[i].vat_type as VatType) === "standard" ? a : 0),
    0,
  );
  const entered = lineAgorot.reduce((s, a) => s + a, 0);
  let vat: number;
  let subtotal: number;
  let total: number;
  if (pricesIncludeVat) {
    vat = toAgorot((taxable / 100) * (vatRate / (1 + vatRate)));
    total = entered;
    subtotal = total - vat;
  } else {
    vat = toAgorot((taxable / 100) * vatRate);
    subtotal = entered;
    total = subtotal + vat;
  }
  return {
    lineTotals: lineAgorot.map((a) => a / 100),
    subtotal: subtotal / 100,
    vat: vat / 100,
    total: total / 100,
  };
}
