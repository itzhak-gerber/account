import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { LineInput } from "../../api/types";
import { fixtureBody } from "../../test/apiFixtures";
import { EMPTY_LINE } from "./helpers";
import { StockWarning } from "./StockWarning";

function show(lines: LineInput[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async (input: RequestInfo | URL) =>
        new Response(JSON.stringify(fixtureBody(String(input))), {
          headers: { "Content-Type": "application/json" },
        }),
    ),
  );
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <StockWarning businessId="b1" lines={lines} />
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("StockWarning", () => {
  it("adds kit components to the product sold on its own", async () => {
    // 3 keyboards in stock: 2 on their own plus 2 kits (1 keyboard each) need 4.
    show([
      { ...EMPTY_LINE, item_id: "i2", description: "מקלדת", quantity: "2" },
      { ...EMPTY_LINE, item_id: "i3", description: "ערכה", quantity: "2" },
    ]);
    expect(await screen.findByRole("alert")).toHaveTextContent("מקלדת אלחוטית: נדרש 4, במלאי 3");
  });

  it("stays quiet when there is enough", async () => {
    show([{ ...EMPTY_LINE, item_id: "i2", description: "מקלדת", quantity: "3" }]);
    await new Promise((r) => setTimeout(r, 100));
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
