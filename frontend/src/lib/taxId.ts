/** Check digit used by Israeli ID (ת.ז), dealer (ע.מ) and company (ח.פ) numbers. */
export function isValidIsraeliTaxId(raw: string): boolean {
  const value = raw.replace(/[-\s]/g, "");
  if (!/^\d{5,9}$/.test(value)) return false;
  const digits = value.padStart(9, "0");
  let sum = 0;
  for (let i = 0; i < 9; i++) {
    let n = Number(digits[i]) * (i % 2 === 0 ? 1 : 2);
    if (n > 9) n -= 9;
    sum += n;
  }
  return sum % 10 === 0;
}
