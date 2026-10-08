/**
 * Cleans what the user types into an amount field, as they type: keeps digits and one decimal
 * point, drops thousands separators, currency signs and spaces, and stops at `maxDecimals`
 * digits after the point (2 for money, 3 for quantities). "350", "350.5", "1,250.75" and
 * "₪ 99" all become valid amounts.
 */
export function cleanAmount(raw: string, maxDecimals = 2): string {
  const kept = raw.replace(/[^\d.]/g, "");
  const point = kept.indexOf(".");
  if (point === -1) return kept;
  const whole = kept.slice(0, point) || "0";
  const fraction = kept
    .slice(point + 1)
    .replace(/\./g, "")
    .slice(0, maxDecimals);
  return `${whole}.${fraction}`;
}

/** A cleaned amount ready to send: no trailing point ("350." is 350). Empty stays empty. */
export function finishAmount(value: string): string {
  return value.endsWith(".") ? value.slice(0, -1) : value;
}

export function isAmount(value: string, maxDecimals = 2): boolean {
  return new RegExp(`^\\d+(\\.\\d{0,${maxDecimals}})?$`).test(value);
}
