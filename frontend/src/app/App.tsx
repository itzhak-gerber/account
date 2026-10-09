import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router";

import { useMeQuery } from "../auth/useMe";
import { SessionProvider } from "../auth/session";
import { AccessibilityPage } from "../pages/AccessibilityPage";
import { CustomersPage } from "../pages/CustomersPage";
import { DashboardPage } from "../pages/DashboardPage";
import { DocumentPage } from "../pages/DocumentPage";
import { DocumentsPage } from "../pages/DocumentsPage";
import { InventoryPage } from "../pages/InventoryPage";
import { InvitePage } from "../pages/InvitePage";
import { ItemsPage } from "../pages/ItemsPage";
import { LandingPage } from "../pages/LandingPage";
import { NotificationsPage } from "../pages/NotificationsPage";
import { OnboardingPage } from "../pages/OnboardingPage";
import { PlaceholderPage } from "../pages/PlaceholderPage";
import { PurchasingPage } from "../pages/PurchasingPage";
import { ProfilePage } from "../pages/ProfilePage";
import { ReportsPage } from "../pages/ReportsPage";
import { SettingsPage } from "../pages/SettingsPage";
import { RtlThemeProvider } from "../theme/RtlThemeProvider";
import { AppShell } from "./AppShell";
import { NAV_ITEMS } from "./navigation";

function AuthenticatedRoutes() {
  const { data: me, isPending } = useMeQuery();
  const location = useLocation();

  if (isPending) {
    return (
      <Box sx={{ minHeight: "100dvh", display: "grid", placeItems: "center" }}>
        <CircularProgress />
      </Box>
    );
  }
  if (!me) return <LandingPage />;

  const hasBusiness = me.memberships.length > 0;
  const built = [
    "/",
    "/settings",
    "/documents",
    "/customers",
    "/items",
    "/inventory",
    "/purchasing",
    "/reports",
  ];
  const placeholders = NAV_ITEMS.filter((item) => !built.includes(item.path));

  return (
    <SessionProvider me={me}>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/invite" element={<InvitePage />} />
          <Route path="/profile" element={<ProfilePage />} />
          {hasBusiness ? (
            <>
              <Route index element={<DashboardPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="/documents" element={<DocumentsPage />} />
              <Route path="/documents/:documentId" element={<DocumentPage />} />
              <Route path="/customers" element={<CustomersPage />} />
              <Route path="/items" element={<ItemsPage />} />
              <Route path="/inventory" element={<InventoryPage />} />
              <Route path="/purchasing" element={<PurchasingPage />} />
              <Route path="/reports" element={<ReportsPage />} />
              <Route path="/notifications" element={<NotificationsPage />} />
              {placeholders.map((item) => (
                <Route
                  key={item.path}
                  path={item.path}
                  element={<PlaceholderPage titleKey={item.labelKey} />}
                />
              ))}
            </>
          ) : (
            <Route index element={<OnboardingPage />} />
          )}
          <Route
            path="*"
            element={<Navigate to="/" replace state={{ from: location.pathname }} />}
          />
        </Route>
      </Routes>
    </SessionProvider>
  );
}

export function App() {
  const [queryClient] = useState(
    () => new QueryClient({ defaultOptions: { queries: { retry: 1 } } }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <RtlThemeProvider>
        <Routes>
          {/* Public: the accessibility statement must be reachable without signing in. */}
          <Route path="/accessibility" element={<AccessibilityPage />} />
          <Route path="*" element={<AuthenticatedRoutes />} />
        </Routes>
      </RtlThemeProvider>
    </QueryClientProvider>
  );
}
