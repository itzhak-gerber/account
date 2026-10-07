import Alert from "@mui/material/Alert";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router";

import { api } from "../api/client";
import type { Business, BusinessInput } from "../api/types";
import { useSession } from "../auth/context";
import { can } from "../auth/permissions";
import { AuditTab } from "../features/settings/AuditTab";
import { BusinessForm } from "../features/settings/BusinessForm";
import { LogoCard } from "../features/settings/LogoCard";
import { NumberingTab } from "../features/settings/NumberingTab";
import { TeamTab } from "../features/settings/TeamTab";
import { errorMessage } from "../lib/errors";

type TabKey = "details" | "team" | "numbering" | "audit";

export function SettingsPage() {
  const { t } = useTranslation();
  const { current, refresh } = useSession();
  const queryClient = useQueryClient();
  const [params] = useSearchParams();
  const [tab, setTab] = useState<TabKey>(() => (params.get("tab") as TabKey | null) ?? "details");

  const save = useMutation({
    mutationFn: (input: BusinessInput) =>
      api.patch<Business>(`/businesses/${current!.business.id}`, input),
    onSuccess: async () => {
      await refresh();
      await queryClient.invalidateQueries({ queryKey: ["business", current!.business.id] });
    },
  });

  if (!current) return null;
  const { business, role } = current;
  const tabs: TabKey[] = ["details"];
  if (can(role, "viewMembers")) tabs.push("team");
  tabs.push("numbering");
  if (can(role, "viewAudit")) tabs.push("audit");

  return (
    <Stack spacing={3} sx={{ maxWidth: 960 }}>
      <Typography variant="h4" component="h1" sx={{ fontWeight: 700 }}>
        {t("settings.title")}
      </Typography>
      <Tabs
        value={tab}
        onChange={(_, value: TabKey) => setTab(value)}
        variant="scrollable"
        allowScrollButtonsMobile
      >
        {tabs.map((key) => (
          <Tab
            key={key}
            value={key}
            label={t(`settings.tab${key[0].toUpperCase()}${key.slice(1)}`)}
          />
        ))}
      </Tabs>

      {tab === "details" && <LogoCard business={business} canEdit={can(role, "manageBusiness")} />}
      {tab === "details" && (
        <Card variant="outlined">
          <CardContent>
            {!can(role, "manageBusiness") && (
              <Alert severity="info" sx={{ mb: 2 }}>
                {t("business.readOnly")}
              </Alert>
            )}
            {save.isError && (
              <Alert severity="error" sx={{ mb: 2 }}>
                {errorMessage(t, save.error)}
              </Alert>
            )}
            {save.isSuccess && (
              <Alert severity="success" sx={{ mb: 2 }}>
                {t("business.saved")}
              </Alert>
            )}
            <BusinessForm
              key={business.id}
              initial={business}
              submitLabel={t("business.save")}
              disabled={!can(role, "manageBusiness")}
              busy={save.isPending}
              onSubmit={(value) => save.mutate(value)}
            />
          </CardContent>
        </Card>
      )}
      {tab === "team" && <TeamTab businessId={business.id} role={role} />}
      {tab === "numbering" && (
        <NumberingTab businessId={business.id} canEdit={can(role, "manageBusiness")} />
      )}
      {tab === "audit" && <AuditTab businessId={business.id} />}
    </Stack>
  );
}
