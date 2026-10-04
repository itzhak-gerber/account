import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { Route, Routes } from "react-router";

import { DashboardPage } from "../pages/DashboardPage";
import { PlaceholderPage } from "../pages/PlaceholderPage";
import { RtlThemeProvider } from "../theme/RtlThemeProvider";
import { AppShell } from "./AppShell";
import { NAV_ITEMS } from "./navigation";

export function App() {
  const [queryClient] = useState(
    () => new QueryClient({ defaultOptions: { queries: { retry: 1 } } }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <RtlThemeProvider>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<DashboardPage />} />
            {NAV_ITEMS.filter((item) => item.path !== "/").map((item) => (
              <Route
                key={item.path}
                path={item.path}
                element={<PlaceholderPage titleKey={item.labelKey} />}
              />
            ))}
          </Route>
        </Routes>
      </RtlThemeProvider>
    </QueryClientProvider>
  );
}
