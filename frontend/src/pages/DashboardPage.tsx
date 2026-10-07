import WarningAmberRounded from "@mui/icons-material/WarningAmberRounded";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link as RouterLink } from "react-router";

import { api } from "../api/client";
import type { Dashboard, DocumentSummary } from "../api/types";
import { can } from "../auth/permissions";
import { MonthlyColumns } from "../features/reports/MonthlyColumns";
import { SummaryRow } from "../features/reports/SummaryRow";
import { formatMoney } from "../lib/money";
import { DocumentList } from "../features/documents/DocumentList";
import { NewDocumentButton } from "../features/documents/NewDocumentButton";

import { useSystemStatus } from "../api/system";
import { useSession } from "../auth/context";

function BusinessSummary({ businessId }: { businessId: string }) {
  const { t } = useTranslation();
  const { data } = useQuery({
    queryKey: ["business", businessId, "reports", "dashboard"],
    queryFn: () => api.get<Dashboard>(`/businesses/${businessId}/reports/dashboard`),
  });
  if (!data) return null;
  const overdue = data.overdue_documents > 0;
  const chartTitle = data.vat_registered
    ? t("dashboard.incomeChart")
    : t("dashboard.receivedChart");
  return (
    <Stack spacing={2}>
      <SummaryRow
        figures={[
          ...(data.vat_registered
            ? [
                {
                  label: `${t("dashboard.incomeNet")} · ${t("dashboard.thisMonth")}`,
                  value: formatMoney(data.income_net),
                },
                {
                  label: `${t("dashboard.vat")} · ${t("dashboard.thisMonth")}`,
                  value: formatMoney(data.income_vat),
                },
              ]
            : []),
          {
            label: `${t("dashboard.received")} · ${t("dashboard.thisMonth")}`,
            value: formatMoney(data.received),
          },
          {
            label: t("dashboard.openBalance"),
            value: formatMoney(data.open_balance),
            note: overdue ? (
              <Stack direction="row" spacing={0.5} sx={{ alignItems: "center" }}>
                <WarningAmberRounded fontSize="small" color="warning" />
                <span>{t("dashboard.overdue", { amount: formatMoney(data.overdue_balance) })}</span>
              </Stack>
            ) : (
              t("dashboard.openDocuments", { count: data.open_documents })
            ),
          },
        ]}
      />
      <Card variant="outlined">
        <CardContent>
          <Stack
            direction="row"
            sx={{ justifyContent: "space-between", alignItems: "center", mb: 2 }}
          >
            <Typography variant="h6" component="h2">
              {chartTitle}
            </Typography>
            <Button component={RouterLink} to="/reports">
              {t("dashboard.toReports")}
            </Button>
          </Stack>
          <MonthlyColumns data={data.income_by_month} title={chartTitle} />
        </CardContent>
      </Card>
    </Stack>
  );
}

function StatusRow({ label, value, ok }: { label: string; value: string; ok?: boolean }) {
  return (
    <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", py: 0.75 }}>
      <Typography color="text.secondary">{label}</Typography>
      {ok === undefined ? (
        <Typography dir="ltr">{value}</Typography>
      ) : (
        <Chip size="small" label={value} color={ok ? "success" : "error"} variant="outlined" />
      )}
    </Stack>
  );
}

export function DashboardPage() {
  const { t } = useTranslation();
  const { data, isPending, isError } = useSystemStatus();
  const { current } = useSession();
  const businessId = current?.business.id;
  const recent = useQuery({
    queryKey: ["business", businessId, "documents", "recent"],
    queryFn: () => api.get<DocumentSummary[]>(`/businesses/${businessId}/documents?limit=5`),
    enabled: Boolean(businessId),
  });

  return (
    <Stack spacing={3} sx={{ maxWidth: 960 }}>
      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={2}
        sx={{ justifyContent: "space-between", alignItems: { xs: "stretch", sm: "center" } }}
      >
        <Box>
          <Typography variant="h4" component="h1" sx={{ fontWeight: 700 }}>
            {t("dashboard.title")}
          </Typography>
          {current && (
            <Typography variant="h6" component="p" color="primary">
              {current.business.display_name} · {t("dashboard.yourRole")}:{" "}
              {t(`roles.${current.role}`)}
            </Typography>
          )}
          <Typography color="text.secondary">{t("dashboard.subtitle")}</Typography>
        </Box>
        <NewDocumentButton />
      </Stack>

      {businessId && can(current?.role, "viewReports") && (
        <BusinessSummary businessId={businessId} />
      )}

      <Stack spacing={1}>
        <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center" }}>
          <Typography variant="h6" component="h2">
            {t("documents.recent")}
          </Typography>
          <Button component={RouterLink} to="/documents">
            {t("documents.viewAll")}
          </Button>
        </Stack>
        <DocumentList documents={recent.data} empty={t("documents.empty")} />
      </Stack>

      <Card variant="outlined" sx={{ maxWidth: 420 }}>
        <CardContent>
          <Typography variant="h6" component="h2" gutterBottom>
            {t("dashboard.systemStatus")}
          </Typography>
          {isPending && <Typography color="text.secondary">{t("dashboard.loading")}</Typography>}
          {isError && <Typography color="error">{t("dashboard.error")}</Typography>}
          {data && (
            <>
              <StatusRow
                label={t("dashboard.server")}
                value={t(`dashboard.${data.status}`)}
                ok={data.status === "ok"}
              />
              <StatusRow
                label={t("dashboard.database")}
                value={t(`dashboard.${data.database}`)}
                ok={data.database === "ok"}
              />
              <StatusRow label={t("dashboard.version")} value={data.version} />
            </>
          )}
        </CardContent>
      </Card>
    </Stack>
  );
}
