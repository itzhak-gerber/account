import Alert from "@mui/material/Alert";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router";

import { useSession } from "../auth/context";
import { BusinessesTab } from "../features/admin/BusinessesTab";
import { PlansTab } from "../features/admin/PlansTab";
import { BillingTab, IndexesTab, NewBusinessTab } from "../features/admin/SettingsTabs";

const TABS = ["businesses", "plans", "settings", "indexes", "billing"] as const;
type TabKey = (typeof TABS)[number];

/** The software operators' screen: plans, subscriptions and billing. The server checks too. */
export function AdminPage() {
  const { t } = useTranslation();
  const { me } = useSession();
  const [params] = useSearchParams();
  const [tab, setTab] = useState<TabKey>(() => {
    const asked = params.get("tab");
    return TABS.find((k) => k === asked) ?? "businesses";
  });

  return (
    <Stack spacing={3} sx={{ maxWidth: 1200 }}>
      <Typography variant="h4" component="h1" sx={{ fontWeight: 700 }}>
        {t("admin.title")}
      </Typography>
      {!me.is_operator ? (
        <Alert severity="info">{t("errors.operator_only")}</Alert>
      ) : (
        <>
          <Tabs
            value={tab}
            onChange={(_, value: TabKey) => setTab(value)}
            variant="scrollable"
            allowScrollButtonsMobile
          >
            {TABS.map((key) => (
              <Tab key={key} value={key} label={t(`admin.tabs.${key}`)} />
            ))}
          </Tabs>
          {tab === "businesses" && <BusinessesTab />}
          {tab === "plans" && <PlansTab />}
          {tab === "settings" && <NewBusinessTab />}
          {tab === "indexes" && <IndexesTab />}
          {tab === "billing" && <BillingTab />}
        </>
      )}
    </Stack>
  );
}
