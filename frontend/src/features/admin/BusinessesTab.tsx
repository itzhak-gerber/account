import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
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
import type { AdminBusiness, Plan, Subscription } from "../../api/types";
import { cleanAmount } from "../../lib/amount";
import { errorMessage } from "../../lib/errors";
import { formatDate, formatMoney } from "../../lib/money";

function SubscriptionsDialog({
  business,
  onClose,
}: {
  business: AdminBusiness;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const base = `/admin/businesses/${business.id}/subscriptions`;
  const history = useQuery({
    queryKey: ["admin", "subscriptions", business.id],
    queryFn: () => api.get<Subscription[]>(base),
  });
  const plans = useQuery({
    queryKey: ["admin", "plans"],
    queryFn: () => api.get<Plan[]>("/admin/plans"),
  });
  const [form, setForm] = useState({
    plan_id: "",
    starts_on: "",
    price: "",
    discount: "",
    notes: "",
  });
  const [ending, setEnding] = useState<{ id: string; date: string } | null>(null);
  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["admin", "subscriptions", business.id] });
    await queryClient.invalidateQueries({ queryKey: ["admin", "businesses"] });
  };
  const assign = useMutation({
    mutationFn: () =>
      api.post<Subscription>(base, {
        plan_id: form.plan_id,
        starts_on: form.starts_on || null,
        price: form.price || null,
        discount_percent: form.discount || null,
        notes: form.notes,
      }),
    onSuccess: async () => {
      setForm({ plan_id: "", starts_on: "", price: "", discount: "", notes: "" });
      await refresh();
    },
  });
  const end = useMutation({
    mutationFn: (e: { id: string; date: string }) =>
      api.post<Subscription>(`${base}/${e.id}/end`, { ends_on: e.date }),
    onSuccess: async () => {
      setEnding(null);
      await refresh();
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (form.plan_id) assign.mutate();
  };

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>{t("admin.subscriptions", { name: business.display_name })}</DialogTitle>
      <DialogContent>
        <Stack spacing={3}>
          <TableContainer
            tabIndex={0}
            role="region"
            aria-label={t("admin.subscriptions", { name: business.display_name })}
          >
            <Table
              size="small"
              aria-label={t("admin.subscriptions", { name: business.display_name })}
            >
              <TableHead>
                <TableRow>
                  <TableCell>{t("admin.plan")}</TableCell>
                  <TableCell>{t("admin.starts")}</TableCell>
                  <TableCell>{t("admin.ends")}</TableCell>
                  <TableCell align="left">{t("admin.price")}</TableCell>
                  <TableCell align="left">{t("admin.discount")}</TableCell>
                  <TableCell>{t("admin.notes")}</TableCell>
                  <TableCell>{t("admin.manage")}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {history.data?.map((s) => (
                  <TableRow key={s.id}>
                    <TableCell>
                      {s.terms.name ?? ""}{" "}
                      <Chip size="small" variant="outlined" label={t(`plan.kinds.${s.kind}`)} />
                    </TableCell>
                    <TableCell>{formatDate(s.starts_on)}</TableCell>
                    <TableCell>{s.ends_on ? formatDate(s.ends_on) : t("plan.noEnd")}</TableCell>
                    <TableCell align="left">{formatMoney(s.price)}</TableCell>
                    <TableCell align="left">{Number(s.discount_percent)}</TableCell>
                    <TableCell>{s.notes}</TableCell>
                    <TableCell>
                      <Button size="small" onClick={() => setEnding({ id: s.id, date: "" })}>
                        {t("admin.endNow")}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>

          {ending && (
            <Stack
              direction={{ xs: "column", sm: "row" }}
              spacing={2}
              sx={{ alignItems: "center" }}
            >
              <TextField
                type="date"
                label={t("admin.endOn")}
                value={ending.date}
                onChange={(e) => setEnding({ ...ending, date: e.target.value })}
                slotProps={{ inputLabel: { shrink: true } }}
              />
              <Button
                variant="contained"
                disabled={!ending.date || end.isPending}
                onClick={() => end.mutate(ending)}
              >
                {t("admin.save")}
              </Button>
              <Button onClick={() => setEnding(null)}>{t("admin.cancel")}</Button>
            </Stack>
          )}
          {end.isError && <Alert severity="error">{errorMessage(t, end.error)}</Alert>}

          <form onSubmit={submit} noValidate>
            <Stack spacing={2}>
              <Typography variant="h6" component="h3">
                {t("admin.assign")}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {t("admin.assignHelp")}
              </Typography>
              <Grid container spacing={2}>
                <Grid size={{ xs: 12, sm: 6 }}>
                  <TextField
                    select
                    required
                    fullWidth
                    label={t("admin.plan")}
                    value={form.plan_id}
                    onChange={(e) => setForm({ ...form, plan_id: e.target.value })}
                  >
                    {plans.data?.map((p) => (
                      <MenuItem key={p.id} value={p.id}>
                        {p.name} · {p.current_price === null ? "—" : formatMoney(p.current_price)}
                      </MenuItem>
                    ))}
                  </TextField>
                </Grid>
                <Grid size={{ xs: 12, sm: 6 }}>
                  <TextField
                    type="date"
                    fullWidth
                    label={t("admin.startsOn")}
                    value={form.starts_on}
                    onChange={(e) => setForm({ ...form, starts_on: e.target.value })}
                    slotProps={{ inputLabel: { shrink: true } }}
                  />
                </Grid>
                <Grid size={{ xs: 6 }}>
                  <TextField
                    fullWidth
                    label={t("admin.priceOverride")}
                    value={form.price}
                    onChange={(e) => setForm({ ...form, price: cleanAmount(e.target.value) })}
                    slotProps={{ htmlInput: { dir: "ltr", inputMode: "decimal" } }}
                  />
                </Grid>
                <Grid size={{ xs: 6 }}>
                  <TextField
                    fullWidth
                    label={t("admin.discountOverride")}
                    value={form.discount}
                    onChange={(e) => setForm({ ...form, discount: cleanAmount(e.target.value) })}
                    slotProps={{ htmlInput: { dir: "ltr", inputMode: "decimal" } }}
                  />
                </Grid>
                <Grid size={12}>
                  <TextField
                    fullWidth
                    label={t("admin.notes")}
                    value={form.notes}
                    onChange={(e) => setForm({ ...form, notes: e.target.value })}
                  />
                </Grid>
              </Grid>
              {assign.isError && <Alert severity="error">{errorMessage(t, assign.error)}</Alert>}
              <div>
                <Button
                  type="submit"
                  variant="contained"
                  disabled={!form.plan_id || assign.isPending}
                >
                  {t("admin.assign")}
                </Button>
              </div>
            </Stack>
          </form>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t("plan.close")}</Button>
      </DialogActions>
    </Dialog>
  );
}

export function BusinessesTab() {
  const { t } = useTranslation();
  const [managing, setManaging] = useState<AdminBusiness | null>(null);
  const businesses = useQuery({
    queryKey: ["admin", "businesses"],
    queryFn: () => api.get<AdminBusiness[]>("/admin/businesses"),
  });

  return (
    <Stack spacing={2}>
      {businesses.isError && <Alert severity="error">{errorMessage(t, businesses.error)}</Alert>}
      <Card variant="outlined">
        <TableContainer tabIndex={0} role="region" aria-label={t("admin.tabs.businesses")}>
          <Table size="small" aria-label={t("admin.tabs.businesses")}>
            <TableHead>
              <TableRow>
                <TableCell>{t("admin.business")}</TableCell>
                <TableCell>{t("admin.taxId")}</TableCell>
                <TableCell>{t("admin.owner")}</TableCell>
                <TableCell>{t("admin.plan")}</TableCell>
                <TableCell>{t("admin.until")}</TableCell>
                <TableCell align="left">{t("admin.docsMonth")}</TableCell>
                <TableCell align="left">{t("admin.scansMonth")}</TableCell>
                <TableCell>{t("admin.manage")}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {businesses.data?.map((b) => (
                <TableRow key={b.id}>
                  <TableCell>{b.display_name}</TableCell>
                  <TableCell dir="ltr" sx={{ textAlign: "right" }}>
                    {b.tax_id}
                  </TableCell>
                  <TableCell dir="ltr" sx={{ textAlign: "right" }}>
                    {b.owner_email}
                  </TableCell>
                  <TableCell>
                    {b.kind ? (
                      <>
                        {b.plan_name}{" "}
                        <Chip size="small" variant="outlined" label={t(`plan.kinds.${b.kind}`)} />
                      </>
                    ) : (
                      <Typography
                        component="span"
                        color="warning.main"
                        sx={{ fontSize: "inherit" }}
                      >
                        {t("admin.noPlan")}
                      </Typography>
                    )}
                  </TableCell>
                  <TableCell>
                    {b.ends_on ? formatDate(b.ends_on) : b.kind ? t("plan.noEnd") : ""}
                  </TableCell>
                  <TableCell align="left">{b.documents_this_month}</TableCell>
                  <TableCell align="left">{b.scans_this_month}</TableCell>
                  <TableCell>
                    <Button size="small" onClick={() => setManaging(b)}>
                      {t("admin.manage")}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </Card>
      {managing && <SubscriptionsDialog business={managing} onClose={() => setManaging(null)} />}
    </Stack>
  );
}
