import { describe, expect, it } from "vitest";

import { cleanAmount, finishAmount, isAmount } from "./amount";

describe("cleanAmount", () => {
  it.each([
    ["350", "350"],
    ["350.5", "350.5"],
    ["350.", "350."],
    ["1,250.75", "1250.75"],
    ["₪ 99", "99"],
    ["350.555", "350.55"],
    ["1.2.3", "1.23"],
    [".5", "0.5"],
  ])("%s -> %s", (raw, cleaned) => expect(cleanAmount(raw)).toBe(cleaned));

  it("allows three decimals for quantities", () => expect(cleanAmount("1.2345", 3)).toBe("1.234"));
});

describe("finishAmount / isAmount", () => {
  it("drops a trailing point", () => expect(finishAmount("350.")).toBe("350"));
  it("accepts whole and partial decimals", () => {
    expect(isAmount("350")).toBe(true);
    expect(isAmount("350.5")).toBe(true);
    expect(isAmount("350.")).toBe(true);
    expect(isAmount("")).toBe(false);
    expect(isAmount("abc")).toBe(false);
  });
});
