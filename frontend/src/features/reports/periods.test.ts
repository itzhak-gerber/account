import { describe, expect, it } from "vitest";

import { presetPeriod } from "./periods";

describe("presetPeriod", () => {
  it("covers this month up to today", () => {
    expect(presetPeriod("thisMonth", "2026-10-07")).toEqual({
      from: "2026-10-01",
      to: "2026-10-07",
    });
  });

  it("gives the whole previous month, across a year boundary", () => {
    expect(presetPeriod("lastMonth", "2026-03-15")).toEqual({
      from: "2026-02-01",
      to: "2026-02-28",
    });
    expect(presetPeriod("lastMonth", "2026-01-05")).toEqual({
      from: "2025-12-01",
      to: "2025-12-31",
    });
  });

  it("gives the last completed two-month VAT period", () => {
    expect(presetPeriod("vatPeriod", "2026-10-07")).toEqual({
      from: "2026-07-01",
      to: "2026-08-31",
    });
    expect(presetPeriod("vatPeriod", "2026-12-20")).toEqual({
      from: "2026-09-01",
      to: "2026-10-31",
    });
    expect(presetPeriod("vatPeriod", "2026-02-10")).toEqual({
      from: "2025-11-01",
      to: "2025-12-31",
    });
    expect(presetPeriod("vatPeriod", "2028-04-01")).toEqual({
      from: "2028-01-01",
      to: "2028-02-29",
    });
  });

  it("gives this year to date and the whole last year", () => {
    expect(presetPeriod("thisYear", "2026-10-07")).toEqual({
      from: "2026-01-01",
      to: "2026-10-07",
    });
    expect(presetPeriod("lastYear", "2026-10-07")).toEqual({
      from: "2025-01-01",
      to: "2025-12-31",
    });
  });
});
