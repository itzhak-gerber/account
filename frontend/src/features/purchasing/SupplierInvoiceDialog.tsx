import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControlLabel from "@mui/material/FormControlLabel";
import Grid from "@mui/material/Grid";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { PurchaseOrder, SupplierInvoice, SupplierInvoiceInput } from "../../api/types";
import { cleanAmount, finishAmount } from "../../lib/amount";
import { errorMessage } from "../../lib/errors";
import { formatMoney } from "../../lib/money";
import { israelToday } from "../documents/helpers";
import { SupplierPicker } from "./SupplierPicker";

const VAT_RATE = 0.18;
const vatOf = (net: string) => (net === "" ? "" : (Number(net) * VAT_RATE).toFixed(2));
const money = (value: string) => String(Number(value));

/** An invoice received from a supplier: amounts as printed on it, and when it was paid. */
export function SupplierInvoiceDialog({
  businessId,
  invoice,
  onClose,
}: {
  businessId: string;
  invoice: SupplierInvoice | null;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const fullScreen = useMediaQuery(useTheme().breakpoints.down("sm"));
  const queryClient = useQueryClient();
  const [value, setValue] = useState<SupplierInvoiceInput>(
    invoice
      ? {
          ...invoice,
          supplier_id: invoice.supplier.id,
          net_amount: money(invoice.net_amount),
          vat_amount: money(invoice.vat_amount),
        }
      : {
          supplier_id: "",
          purchase_order_id: null,
          invoice_number: "",
          invoice_date: israelToday(),
          due_date: null,
          net_amount: "",
          vat_amount: "",
          paid_date: null,
          notes: "",
        },
  );
  // VAT follows the net amount until it is typed in by hand (e.g. part of the invoice exempt).
  const [vatByHand, setVatByHand] = useState(Boolean(invoice));
  const [touched, setTouched] = useState(false);
  const orders = useQuery({
    queryKey: ["business", businessId, "purchase-orders"],
    queryFn: () => api.get<PurchaseOrder[]>(`/businesses/${businessId}/purchase-orders`),
  });
  const supplierOrders = (orders.data ?? []).filter((o) => o.supplier.id === value.supplier_id);
  const base = `/businesses/${businessId}/supplier-invoices`;
  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["business", businessId, "supplier-invoices"] });

  const save = useMutation({
    mutationFn: () => {
      const body = {
        ...value,
        invoice_number: value.invoice_number.trim(),
        net_amount: finishAmount(value.net_amount),
        vat_amount: finishAmount(value.vat_amount),
        due_date: value.due_date || null,
        paid_date: value.paid_date || null,
      };
      if (!invoice) return api.post<SupplierInvoice>(base, body);
      const { supplier_id: _supplier, ...patch } = body;
      return api.patch<SupplierInvoice>(`${base}/${invoice.id}`, patch);
    },
    onSuccess: async () => {
      await invalidate();
      onClose();
    },
  });
  const remove = useMutation({
    mutationFn: () => api.delete(`${base}/${invoice!.id}`),
    onSuccess: async () => {
      await invalidate();
      onClose();
    },
  });

  const set = (patch: Partial<SupplierInvoiceInput>) => setValue((v) => ({ ...v, ...patch }));
  const ok =
    value.supplier_id !== "" &&
    value.invoice_number.trim() !== "" &&
    value.invoice_date !== "" &&
    value.net_amount !== "" &&
    value.vat_amount !== "";
  const total = (Number(value.net_amount) || 0) + (Number(value.vat_amount) || 0);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (ok) save.mutate();
  };
  const required = (filled: boolean) =>
    touched && !filled ? { error: true, helperText: t("common.required") } : {};
  const ltr = { htmlInput: { dir: "ltr", inputMode: "decimal" } } as const;

  return (
    <Dialog open onClose={onClose} fullScreen={fullScreen} maxWidth="sm" fullWidth>
      <form onSubmit={submit} noValidate>
        <DialogTitle>
          {invoice ? t("supplierInvoices.edit") : t("supplierInvoices.new")}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            {(save.isError || remove.isError) && (
              <Alert severity="error">{errorMessage(t, save.error ?? remove.error)}</Alert>
            )}
            <SupplierPicker
              businessId={businessId}
              value={value.supplier_id}
              onChange={(id) => set({ supplier_id: id, purchase_order_id: null })}
              disabled={Boolean(invoice)}
              error={touched && !value.supplier_id}
            />
            <Grid container spacing={2}>
              <Grid size={{ xs: 12, sm: 4 }}>
                <TextField
                  label={t("supplierInvoices.number")}
                  value={value.invoice_number}
                  onChange={(e) => set({ invoice_number: e.target.value })}
                  fullWidth
                  required
                  {...required(value.invoice_number.trim() !== "")}
                />
              </Grid>
              <Grid size={{ xs: 6, sm: 4 }}>
                <TextField
                  type="date"
                  label={t("supplierInvoices.date")}
                  value={value.invoice_date}
                  onChange={(e) => set({ invoice_date: e.target.value })}
                  fullWidth
                  required
                  slotProps={{ inputLabel: { shrink: true } }}
                />
              </Grid>
              <Grid size={{ xs: 6, sm: 4 }}>
                <TextField
                  type="date"
                  label={t("supplierInvoices.dueDate")}
                  value={value.due_date ?? ""}
                  onChange={(e) => set({ due_date: e.target.value || null })}
                  fullWidth
                  slotProps={{ inputLabel: { shrink: true } }}
                />
              </Grid>
              <Grid size={{ xs: 6, sm: 4 }}>
                <TextField
                  label={t("supplierInvoices.net")}
                  value={value.net_amount}
                  onChange={(e) => {
                    const net = cleanAmount(e.target.value);
                    set(
                      vatByHand ? { net_amount: net } : { net_amount: net, vat_amount: vatOf(net) },
                    );
                  }}
                  fullWidth
                  required
                  slotProps={ltr}
                  {...required(value.net_amount !== "")}
                />
              </Grid>
              <Grid size={{ xs: 6, sm: 4 }}>
                <TextField
                  label={t("supplierInvoices.vat")}
                  value={value.vat_amount}
                  onChange={(e) => {
                    setVatByHand(true);
                    set({ vat_amount: cleanAmount(e.target.value) });
                  }}
                  fullWidth
                  required
                  slotProps={ltr}
                  {...required(value.vat_amount !== "")}
                />
              </Grid>
              <Grid size={{ xs: 12, sm: 4 }} sx={{ display: "flex", alignItems: "center" }}>
                <Typography sx={{ fontWeight: 600 }}>
                  {t("supplierInvoices.total")}: {formatMoney(total)}
                </Typography>
              </Grid>
            </Grid>
            {supplierOrders.length > 0 && (
              <TextField
                select
                label={t("supplierInvoices.order")}
                value={value.purchase_order_id ?? ""}
                onChange={(e) => set({ purchase_order_id: e.target.value || null })}
              >
                <MenuItem value="">{t("supplierInvoices.noOrder")}</MenuItem>
                {supplierOrders.map((o) => (
                  <MenuItem key={o.id} value={o.id}>
                    {t("orders.open", { number: o.number })} · {formatMoney(o.total)}
                  </MenuItem>
                ))}
              </TextField>
            )}
            <Stack direction="row" spacing={2} sx={{ alignItems: "center", flexWrap: "wrap" }}>
              <FormControlLabel
                control={
                  <Switch
                    checked={value.paid_date !== null}
                    onChange={(e) => set({ paid_date: e.target.checked ? israelToday() : null })}
                  />
                }
                label={t("supplierInvoices.paid")}
              />
              {value.paid_date !== null && (
                <TextField
                  type="date"
                  size="small"
                  label={t("supplierInvoices.paidDate")}
                  value={value.paid_date}
                  onChange={(e) => set({ paid_date: e.target.value || israelToday() })}
                  slotProps={{ inputLabel: { shrink: true } }}
                />
              )}
            </Stack>
            <TextField
              label={t("purchasing.notes")}
              value={value.notes}
              onChange={(e) => set({ notes: e.target.value })}
              multiline
              minRows={2}
            />
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          {invoice && (
            <Button
              color="error"
              disabled={remove.isPending}
              onClick={() => window.confirm(t("supplierInvoices.confirmDelete")) && remove.mutate()}
              sx={{ me: "auto" }}
            >
              {t("supplierInvoices.delete")}
            </Button>
          )}
          <Button onClick={onClose}>{t("common.cancel")}</Button>
          <Button type="submit" variant="contained" disabled={save.isPending}>
            {t("purchasing.save")}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
