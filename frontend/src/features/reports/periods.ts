export type PresetKey =
  "thisMonth" | "lastMonth" | "vatPeriod" | "thisYear" | "lastYear" | "custom";

export const PRESETS: PresetKey[] = [
  "thisMonth",
  "lastMonth",
  "vatPeriod",
  "thisYear",
  "lastYear",
  "custom",
];

export interface Period {
  from: string;
  to: string;
}

function iso(year: number, month: number, day: number): string {
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

function lastDay(year: number, month: number): number {
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

/** A whole-months period; months may run below 1 (previous year). */
function months(year: number, firstMonth: number, lastMonth: number): Period {
  const start = new Date(Date.UTC(year, firstMonth - 1, 1));
  const end = new Date(Date.UTC(year, lastMonth - 1, 1));
  const ey = end.getUTCFullYear();
  const em = end.getUTCMonth() + 1;
  return {
    from: iso(start.getUTCFullYear(), start.getUTCMonth() + 1, 1),
    to: iso(ey, em, lastDay(ey, em)),
  };
}

/**
 * The period for a preset, given today's date (YYYY-MM-DD, Israel time).
 * "vatPeriod" is the last completed two-month VAT period (Jan–Feb, Mar–Apr, …), the one
 * most small businesses report next.
 */
export function presetPeriod(preset: Exclude<PresetKey, "custom">, today: string): Period {
  const [year, month] = today.split("-").map(Number);
  switch (preset) {
    case "thisMonth":
      return { from: iso(year, month, 1), to: today };
    case "lastMonth":
      return months(year, month - 1, month - 1);
    case "vatPeriod": {
      const currentStart = month - ((month - 1) % 2);
      return months(year, currentStart - 2, currentStart - 1);
    }
    case "thisYear":
      return { from: iso(year, 1, 1), to: today };
    case "lastYear":
      return months(year - 1, 1, 12);
  }
}

export function monthLabel(isoMonth: string, style: "short" | "long" = "long"): string {
  const [y, m] = isoMonth.split("-").map(Number);
  return new Intl.DateTimeFormat("he-IL", {
    month: style,
    year: style === "long" ? "numeric" : undefined,
    timeZone: "UTC",
  }).format(new Date(Date.UTC(y, m - 1, 1)));
}
