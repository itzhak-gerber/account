import FileDownloadOutlined from "@mui/icons-material/FileDownloadOutlined";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import type { UseQueryResult } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router";

import type { IncomeReport, OpenBalancesReport, ReceiptsReport } from "../api/types";
import { useSession } from "../auth/context";
import { can } from "../auth/permissions";
import { israelToday } from "../features/documents/helpers";
import { excelFilename, excelUrl, useReport, type ReportName } from "../features/reports/hooks";
import { PeriodPicker } from "../features/reports/PeriodPicker";
import { presetPeriod, type Period, type PresetKey } from "../features/reports/periods";
import { IncomeView, OpenBalancesView, ReceiptsView } from "../features/reports/ReportViews";
import { errorMessage } from "../lib/errors";

const TABS: ReportName[] = ["income", "receipts", "open_balances"];
const VAT_REGISTERED = ["licensed_dealer", "company"];

function Loaded<T>({
  result,
  children,
}: {
  result: UseQueryResult<T>;
  children: (data: T) => ReactNode;
}) {
  const { t } = useTranslation();
  if (result.isPending)
    return (
      <Box sx={{ display: "grid", placeItems: "center", py: 6 }}>
        <CircularProgress />
      </Box>
    );
  if (result.isError) return <Alert severity="error">{errorMessage(t, result.error)}</Alert>;
  return <>{children(result.data)}</>;
}

function IncomeTab({ businessId, period }: { businessId: string; period: Period }) {
  const result = useReport<IncomeReport>(businessId, "income", period);
  return <Loaded result={result}>{(data) => <IncomeView report={data} />}</Loaded>;
}

function ReceiptsTab({ businessId, period }: { businessId: string; period: Period }) {
  const result = useReport<ReceiptsReport>(businessId, "receipts", period);
  return <Loaded result={result}>{(data) => <ReceiptsView report={data} />}</Loaded>;
}

function OpenBalancesTab({ businessId }: { businessId: string }) {
  const result = useReport<OpenBalancesReport>(businessId, "open_balances", null);
  return <Loaded result={result}>{(data) => <OpenBalancesView report={data} />}</Loaded>;
}

export function ReportsPage() {
  const { t } = useTranslation();
  const { current } = useSession();
  const businessId = current!.business.id;
  const vatRegistered = VAT_REGISTERED.includes(current!.business.business_type);
  const tabs = vatRegistered ? TABS : TABS.filter((tab) => tab !== "income");
  const [params, setParams] = useSearchParams();
  const requested = params.get("tab") as ReportName | null;
  const report = requested && tabs.includes(requested) ? requested : tabs[0];
  const [preset, setPreset] = useState<PresetKey>("thisMonth");
  const [period, setPeriod] = useState<Period>(() => presetPeriod("thisMonth", israelToday()));
  const usesPeriod = report !== "open_balances";
  const validPeriod = period.from <= period.to;

  if (!can(current?.role, "viewReports")) {
    return <Alert severity="info">{t("reports.noPermission")}</Alert>;
  }

  return (
    <Stack spacing={3} sx={{ maxWidth: 1200, minWidth: 0 }}>
      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={2}
        sx={{ justifyContent: "space-between", alignItems: { xs: "stretch", sm: "center" } }}
      >
        <Box>
          <Typography variant="h4" component="h1" sx={{ fontWeight: 700 }}>
            {t("reports.title")}
          </Typography>
          <Typography color="text.secondary">{t("reports.subtitle")}</Typography>
        </Box>
        <Button
          variant="outlined"
          startIcon={<FileDownloadOutlined />}
          href={excelUrl(businessId, report, usesPeriod ? period : null)}
          download={excelFilename(report, usesPeriod ? period : null, israelToday())}
          disabled={usesPeriod && !validPeriod}
        >
          {t("reports.export")}
        </Button>
      </Stack>

      <Tabs
        value={report}
        onChange={(_, value: ReportName) => setParams({ tab: value }, { replace: true })}
        variant="scrollable"
        allowScrollButtonsMobile
      >
        {tabs.map((tab) => (
          <Tab key={tab} value={tab} label={t(`reports.tabs.${tab}`)} />
        ))}
      </Tabs>

      {usesPeriod && (
        <PeriodPicker
          preset={preset}
          period={period}
          onChange={(nextPreset, nextPeriod) => {
            setPreset(nextPreset);
            setPeriod(nextPeriod);
          }}
        />
      )}
      <Typography variant="body2" color="text.secondary">
        {report === "income"
          ? t("reports.incomeHelp")
          : report === "receipts"
            ? t("reports.receiptsHelp")
            : t("reports.openHelp")}
        {!vatRegistered && report === "receipts" && ` ${t("reports.notVatRegistered")}`}
      </Typography>

      {usesPeriod && !validPeriod ? (
        <Alert severity="warning">{t("errors.invalid_period")}</Alert>
      ) : (
        <>
          {report === "income" && <IncomeTab businessId={businessId} period={period} />}
          {report === "receipts" && <ReceiptsTab businessId={businessId} period={period} />}
          {report === "open_balances" && <OpenBalancesTab businessId={businessId} />}
        </>
      )}
    </Stack>
  );
}
