import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

describe("App", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({ status: "ok", version: "0.1.0", environment: "test", database: "ok" }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        ),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the Hebrew dashboard with system status", async () => {
    renderAt("/");

    expect(screen.getByRole("heading", { name: "ברוכים הבאים" })).toBeInTheDocument();
    expect(await screen.findByText("0.1.0")).toBeInTheDocument();
    expect(screen.getAllByText("תקין")).toHaveLength(2);
  });

  it("shows a placeholder page for upcoming sections", () => {
    renderAt("/customers");

    expect(screen.getByRole("heading", { name: "לקוחות" })).toBeInTheDocument();
    expect(screen.getByText("בקרוב")).toBeInTheDocument();
  });
});
