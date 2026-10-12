import AddIcon from "@mui/icons-material/Add";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControlLabel from "@mui/material/FormControlLabel";
import FormGroup from "@mui/material/FormGroup";
import FormLabel from "@mui/material/FormLabel";
import Grid from "@mui/material/Grid";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
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
import type { Linkage, ModuleName, Plan, PlanInput } from "../../api/types";
import { cleanAmount } from "../../lib/amount";
import { errorMessage } from "../../lib/errors";
import { formatMoney } from "../../lib/money";

const MODULES: ModuleName[] = ["inventory", "scanning"];
const EMPTY: PlanInput = {
  name: "",
  description: "",
  modules: [],
  duration_months: 12,
  price: "",
  linkage: "none",
  base_index: null,
  documents_per_month: null,
  document_overage_price: null,
  scans_per_month: null,
  scan_overage_price: null,
  is_active: true,
};

const toCount = (value: string) => (value.trim() === "" ? null : Number(value.replace(/\D/g, "")));
const toMoney = (value: string) => cleanAmount(value) || null;

function PlanDialog({ plan, onClose }: { plan: Plan | null; onClose: () => void }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [value, setValue] = useState<PlanInput>(plan ? { ...plan } : EMPTY);
  const save = useMutation({
    mutationFn: (input: PlanInput) =>
      plan
        ? api.put<Plan>(`/admin/plans/${plan.id}`, input)
        : api.post<Plan>("/admin/plans", input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["admin", "plans"] });
      onClose();
    },
  });
  const valid = value.name.trim() !== "" && value.price !== "" && value.duration_months > 0;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (valid) save.mutate(value);
  };
  const text = (key: keyof PlanInput, label: string, money = false) => (
    <TextField
      label={label}
      fullWidth
      value={value[key] ?? ""}
      onChange={(e) =>
        setValue((v) => ({
          ...v,
          [key]: money ? toMoney(e.target.value) : toCount(e.target.value),
        }))
      }
      slotProps={{ htmlInput: { dir: "ltr", inputMode: money ? "decimal" : "numeric" } }}
    />
  );

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="md">
      <form onSubmit={submit} noValidate>
        <DialogTitle>{plan ? t("admin.editPlan") : t("admin.newPlan")}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            {plan && <Alert severity="info">{t("admin.planChangeHelp")}</Alert>}
            <Grid container spacing={2}>
              <Grid size={{ xs: 12, sm: 6 }}>
                <TextField
                  label={t("admin.name")}
                  required
                  fullWidth
                  value={value.name}
                  onChange={(e) => setValue((v) => ({ ...v, name: e.target.value }))}
                />
              </Grid>
              <Grid size={{ xs: 12, sm: 6 }}>
                <TextField
                  label={t("admin.description")}
                  fullWidth
                  value={value.description}
                  onChange={(e) => setValue((v) => ({ ...v, description: e.target.value }))}
                />
              </Grid>
              <Grid size={12}>
                <FormLabel component="legend">{t("admin.modules")}</FormLabel>
                <FormGroup row>
                  {MODULES.map((m) => (
                    <FormControlLabel
                      key={m}
                      label={t(`plan.moduleNames.${m}`)}
                      control={
                        <Checkbox
                          checked={value.modules.includes(m)}
                          onChange={(e) =>
                            setValue((v) => ({
                              ...v,
                              modules: e.target.checked
                                ? [...v.modules, m]
                                : v.modules.filter((x) => x !== m),
                            }))
                          }
                        />
                      }
                    />
                  ))}
                </FormGroup>
              </Grid>
              <Grid size={{ xs: 6, sm: 3 }}>
                <TextField
                  label={t("admin.months")}
                  required
                  fullWidth
                  value={value.duration_months || ""}
                  onChange={(e) =>
                    setValue((v) => ({ ...v, duration_months: toCount(e.target.value) ?? 0 }))
                  }
                  slotProps={{ htmlInput: { dir: "ltr", inputMode: "numeric" } }}
                />
              </Grid>
              <Grid size={{ xs: 6, sm: 3 }}>
                <TextField
                  label={t("admin.planPrice")}
                  required
                  fullWidth
                  value={value.price}
                  onChange={(e) => setValue((v) => ({ ...v, price: cleanAmount(e.target.value) }))}
                  slotProps={{ htmlInput: { dir: "ltr", inputMode: "decimal" } }}
                />
              </Grid>
              <Grid size={{ xs: 6, sm: 3 }}>
                <TextField
                  select
                  label={t("admin.linkage")}
                  fullWidth
                  value={value.linkage}
                  onChange={(e) => setValue((v) => ({ ...v, linkage: e.target.value as Linkage }))}
                >
                  {(["none", "cpi", "usd"] as const).map((l) => (
                    <MenuItem key={l} value={l}>
                      {t(`admin.linkages.${l}`)}
                    </MenuItem>
                  ))}
                </TextField>
              </Grid>
              <Grid size={{ xs: 6, sm: 3 }}>
                {value.linkage !== "none" && (
                  <TextField
                    label={t("admin.baseIndex")}
                    fullWidth
                    value={value.base_index ?? ""}
                    onChange={(e) =>
                      setValue((v) => ({
                        ...v,
                        base_index: cleanAmount(e.target.value, 4) || null,
                      }))
                    }
                    slotProps={{ htmlInput: { dir: "ltr", inputMode: "decimal" } }}
                  />
                )}
              </Grid>
              <Grid size={{ xs: 12, sm: 6 }}>
                {text("documents_per_month", t("admin.docsQuota"))}
              </Grid>
              <Grid size={{ xs: 12, sm: 6 }}>
                {text("document_overage_price", t("admin.docOverage"), true)}
              </Grid>
              <Grid size={{ xs: 12, sm: 6 }}>{text("scans_per_month", t("admin.scansQuota"))}</Grid>
              <Grid size={{ xs: 12, sm: 6 }}>
                {text("scan_overage_price", t("admin.scanOverage"), true)}
              </Grid>
              <Grid size={12}>
                <FormControlLabel
                  label={t("admin.active")}
                  control={
                    <Switch
                      checked={value.is_active}
                      onChange={(e) => setValue((v) => ({ ...v, is_active: e.target.checked }))}
                    />
                  }
                />
              </Grid>
            </Grid>
            {save.isError && <Alert severity="error">{errorMessage(t, save.error)}</Alert>}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose}>{t("admin.cancel")}</Button>
          <Button type="submit" variant="contained" disabled={!valid || save.isPending}>
            {t("admin.save")}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}

export function PlansTab() {
  const { t } = useTranslation();
  const [editing, setEditing] = useState<Plan | "new" | null>(null);
  const plans = useQuery({
    queryKey: ["admin", "plans"],
    queryFn: () => api.get<Plan[]>("/admin/plans"),
  });
  const quota = (n: number | null) => (n === null ? t("plan.unlimited") : String(n));

  return (
    <Stack spacing={2}>
      <Button
        variant="contained"
        startIcon={<AddIcon />}
        onClick={() => setEditing("new")}
        sx={{ alignSelf: "flex-start" }}
      >
        {t("admin.newPlan")}
      </Button>
      {plans.isError && <Alert severity="error">{errorMessage(t, plans.error)}</Alert>}
      <Card variant="outlined">
        <TableContainer tabIndex={0} role="region" aria-label={t("admin.tabs.plans")}>
          <Table size="small" aria-label={t("admin.tabs.plans")}>
            <TableHead>
              <TableRow>
                <TableCell>{t("admin.name")}</TableCell>
                <TableCell>{t("admin.modules")}</TableCell>
                <TableCell align="left">{t("admin.months")}</TableCell>
                <TableCell align="left">{t("admin.currentPrice")}</TableCell>
                <TableCell align="left">{t("plan.documents")}</TableCell>
                <TableCell align="left">{t("plan.scans")}</TableCell>
                <TableCell>{t("admin.active")}</TableCell>
                <TableCell>
                  <Typography component="span" sx={{ fontSize: "inherit" }}>
                    {t("admin.manage")}
                  </Typography>
                </TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {plans.data?.map((p) => (
                <TableRow key={p.id}>
                  <TableCell>{p.name}</TableCell>
                  <TableCell>
                    {p.modules.map((m) => t(`plan.moduleNames.${m}`)).join(", ") || "—"}
                  </TableCell>
                  <TableCell align="left">{p.duration_months}</TableCell>
                  <TableCell align="left">
                    {p.current_price === null ? "—" : formatMoney(p.current_price)}
                    {p.linkage !== "none" && ` (${t(`admin.linkages.${p.linkage}`)})`}
                  </TableCell>
                  <TableCell align="left">{quota(p.documents_per_month)}</TableCell>
                  <TableCell align="left">
                    {p.modules.includes("scanning") ? quota(p.scans_per_month) : "—"}
                  </TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      color={p.is_active ? "success" : "default"}
                      variant="outlined"
                      label={p.is_active ? t("admin.active") : t("admin.inactive")}
                    />
                  </TableCell>
                  <TableCell>
                    <Button size="small" onClick={() => setEditing(p)}>
                      {t("admin.editPlan")}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </Card>
      {editing && (
        <PlanDialog plan={editing === "new" ? null : editing} onClose={() => setEditing(null)} />
      )}
    </Stack>
  );
}
