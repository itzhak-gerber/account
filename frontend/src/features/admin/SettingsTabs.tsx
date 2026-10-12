import FileDownloadOutlined from "@mui/icons-material/FileDownloadOutlined";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Grid from "@mui/material/Grid";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { BillingReport, BillingSettings, IndexValue, Plan } from "../../api/types";
import { cleanAmount } from "../../lib/amount";
import { errorMessage } from "../../lib/errors";
import { formatDate, formatMoney } from "../../lib/money";
import { israelToday } from "../documents/helpers";

/** What a new business gets: a trial plan for some days, and a discount on its first periods. */
export function NewBusinessTab() {
  const settings = useQuery({
    queryKey: ["admin", "settings"],
    queryFn: () => api.get<BillingSettings>("/admin/settings"),
  });
  return settings.data ? <NewBusinessForm initial={settings.data} /> : null;
}

function NewBusinessForm({ initial }: { initial: BillingSettings }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const plans = useQuery({
    queryKey: ["admin", "plans"],
    queryFn: () => api.get<Plan[]>("/admin/plans"),
  });
  const [value, setValue] = useState<BillingSettings>(initial);
  const save = useMutation({
    mutationFn: (input: BillingSettings) => api.put<BillingSettings>("/admin/settings", input),
    onSuccess: (data) => queryClient.setQueryData(["admin", "settings"], data),
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate(value);
  };
  const count = (raw: string) => Number(raw.replace(/\D/g, "") || 0);

  return (
    <Card variant="outlined">
      <CardContent>
        <form onSubmit={submit} noValidate>
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, sm: 8 }}>
              <TextField
                select
                fullWidth
                label={t("admin.trialPlan")}
                value={value.trial_plan_id ?? ""}
                onChange={(e) => setValue({ ...value, trial_plan_id: e.target.value || null })}
              >
                <MenuItem value="">{t("admin.noTrial")}</MenuItem>
                {plans.data?.map((p) => (
                  <MenuItem key={p.id} value={p.id}>
                    {p.name}
                  </MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid size={{ xs: 12, sm: 4 }}>
              <TextField
                fullWidth
                label={t("admin.trialDays")}
                value={value.trial_days}
                onChange={(e) => setValue({ ...value, trial_days: count(e.target.value) })}
                slotProps={{ htmlInput: { dir: "ltr", inputMode: "numeric" } }}
              />
            </Grid>
            <Grid size={{ xs: 6 }}>
              <TextField
                fullWidth
                label={t("admin.newDiscount")}
                value={value.new_business_discount_percent}
                onChange={(e) =>
                  setValue({
                    ...value,
                    new_business_discount_percent: cleanAmount(e.target.value) || "0",
                  })
                }
                slotProps={{ htmlInput: { dir: "ltr", inputMode: "decimal" } }}
              />
            </Grid>
            <Grid size={{ xs: 6 }}>
              <TextField
                fullWidth
                label={t("admin.newDiscountPeriods")}
                value={value.new_business_discount_periods}
                onChange={(e) =>
                  setValue({ ...value, new_business_discount_periods: count(e.target.value) })
                }
                slotProps={{ htmlInput: { dir: "ltr", inputMode: "numeric" } }}
              />
            </Grid>
            <Grid size={12}>
              <Stack spacing={2}>
                {save.isError && <Alert severity="error">{errorMessage(t, save.error)}</Alert>}
                {save.isSuccess && <Alert severity="success">{t("admin.saved")}</Alert>}
                <div>
                  <Button type="submit" variant="contained" disabled={save.isPending}>
                    {t("admin.save")}
                  </Button>
                </div>
              </Stack>
            </Grid>
          </Grid>
        </form>
      </CardContent>
    </Card>
  );
}

/** CPI by month and the dollar rate by day, for linked prices. */
export function IndexesTab() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const values = useQuery({
    queryKey: ["admin", "index-values"],
    queryFn: () => api.get<IndexValue[]>("/admin/index-values"),
  });
  const [form, setForm] = useState({ kind: "cpi" as "cpi" | "usd", period: "", value: "" });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["admin"] });
  const add = useMutation({
    mutationFn: () => api.post<IndexValue>("/admin/index-values", form),
    onSuccess: async () => {
      setForm({ ...form, period: "", value: "" });
      await refresh();
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => api.delete(`/admin/index-values/${id}`),
    onSuccess: refresh,
  });

  return (
    <Stack spacing={2}>
      <Typography color="text.secondary">{t("admin.indexHelp")}</Typography>
      <Stack
        component="form"
        direction={{ xs: "column", sm: "row" }}
        spacing={2}
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          if (form.period && form.value) add.mutate();
        }}
      >
        <TextField
          select
          label={t("admin.indexKind")}
          value={form.kind}
          onChange={(e) => setForm({ ...form, kind: e.target.value as "cpi" | "usd" })}
          sx={{ minWidth: 200 }}
        >
          <MenuItem value="cpi">{t("admin.linkages.cpi")}</MenuItem>
          <MenuItem value="usd">{t("admin.linkages.usd")}</MenuItem>
        </TextField>
        <TextField
          type="date"
          label={t("admin.period")}
          value={form.period}
          onChange={(e) => setForm({ ...form, period: e.target.value })}
          slotProps={{ inputLabel: { shrink: true } }}
        />
        <TextField
          label={t("admin.value")}
          value={form.value}
          onChange={(e) => setForm({ ...form, value: cleanAmount(e.target.value, 4) })}
          slotProps={{ htmlInput: { dir: "ltr", inputMode: "decimal" } }}
        />
        <Button
          type="submit"
          variant="contained"
          disabled={!form.period || !form.value || add.isPending}
        >
          {t("admin.addValue")}
        </Button>
      </Stack>
      {add.isError && <Alert severity="error">{errorMessage(t, add.error)}</Alert>}
      <Card variant="outlined">
        <TableContainer tabIndex={0} role="region" aria-label={t("admin.tabs.indexes")}>
          <Table size="small" aria-label={t("admin.tabs.indexes")}>
            <TableHead>
              <TableRow>
                <TableCell>{t("admin.indexKind")}</TableCell>
                <TableCell>{t("admin.period")}</TableCell>
                <TableCell align="left">{t("admin.value")}</TableCell>
                <TableCell>{t("admin.manage")}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {values.data?.map((v) => (
                <TableRow key={v.id}>
                  <TableCell>{t(`admin.linkages.${v.kind}`)}</TableCell>
                  <TableCell>{formatDate(v.period)}</TableCell>
                  <TableCell align="left">{Number(v.value)}</TableCell>
                  <TableCell>
                    <Button size="small" color="error" onClick={() => remove.mutate(v.id)}>
                      {t("admin.delete")}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </Card>
    </Stack>
  );
}

/** What to charge each business for a month: plans bought then, and overage. */
export function BillingTab() {
  const { t } = useTranslation();
  const [month, setMonth] = useState(israelToday().slice(0, 7));
  const report = useQuery({
    queryKey: ["admin", "billing", month],
    queryFn: () => api.get<BillingReport>(`/admin/billing?month=${month}-01`),
    enabled: /^\d{4}-\d{2}$/.test(month),
  });

  return (
    <Stack spacing={2}>
      <Typography color="text.secondary">{t("admin.billingHelp")}</Typography>
      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={2}
        sx={{ alignItems: { sm: "center" } }}
      >
        <TextField
          type="month"
          label={t("admin.month")}
          value={month}
          onChange={(e) => setMonth(e.target.value)}
          slotProps={{ inputLabel: { shrink: true } }}
        />
        <Button
          variant="outlined"
          startIcon={<FileDownloadOutlined />}
          href={`/api/v1/admin/billing?month=${month}-01&format=xlsx`}
          download={`חיובים ${month}.xlsx`}
        >
          {t("admin.download")}
        </Button>
      </Stack>
      {report.isError && <Alert severity="error">{errorMessage(t, report.error)}</Alert>}
      {report.data && report.data.rows.length === 0 && (
        <Typography color="text.secondary">{t("admin.noCharges")}</Typography>
      )}
      {report.data && report.data.rows.length > 0 && (
        <Card variant="outlined">
          <TableContainer tabIndex={0} role="region" aria-label={t("admin.tabs.billing")}>
            <Table size="small" aria-label={t("admin.tabs.billing")}>
              <TableHead>
                <TableRow>
                  <TableCell>{t("admin.business")}</TableCell>
                  <TableCell>{t("admin.taxId")}</TableCell>
                  <TableCell align="left">{t("admin.planCharges")}</TableCell>
                  <TableCell align="left">{t("admin.docsOver")}</TableCell>
                  <TableCell align="left">{t("admin.scansOver")}</TableCell>
                  <TableCell align="left">{t("admin.total")}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {report.data.rows.map((r) => (
                  <TableRow key={r.business_id}>
                    <TableCell>{r.business_name}</TableCell>
                    <TableCell dir="ltr" sx={{ textAlign: "right" }}>
                      {r.tax_id}
                    </TableCell>
                    <TableCell align="left">
                      {formatMoney(r.plan_charges)}
                      {r.plan_names.length > 0 && ` (${r.plan_names.join(", ")})`}
                    </TableCell>
                    <TableCell align="left">
                      {r.documents_over} · {formatMoney(r.documents_over_amount)}
                    </TableCell>
                    <TableCell align="left">
                      {r.scans_over} · {formatMoney(r.scans_over_amount)}
                    </TableCell>
                    <TableCell align="left">{formatMoney(r.total)}</TableCell>
                  </TableRow>
                ))}
                <TableRow>
                  <TableCell colSpan={5} sx={{ fontWeight: 700 }}>
                    {t("admin.total")}
                  </TableCell>
                  <TableCell align="left" sx={{ fontWeight: 700 }}>
                    {formatMoney(report.data.total)}
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </TableContainer>
        </Card>
      )}
    </Stack>
  );
}
