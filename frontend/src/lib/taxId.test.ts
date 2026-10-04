import { describe, expect, it } from "vitest";

import { isValidIsraeliTaxId } from "./taxId";

describe("isValidIsraeliTaxId", () => {
  it.each(["516179157", "123456782", "51-617-9157"])("accepts %s", (value) => {
    expect(isValidIsraeliTaxId(value)).toBe(true);
  });

  it.each(["516179158", "123456789", "12", "abc"])("rejects %s", (value) => {
    expect(isValidIsraeliTaxId(value)).toBe(false);
  });
});
