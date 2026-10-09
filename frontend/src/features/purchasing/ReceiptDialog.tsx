import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Grid from "@mui/material/Grid";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { GoodsReceipt, Item, PurchaseOrder } from "../../api/types";
import { finishAmount } from "../../lib/amount";
import { errorMessage } from "../../lib/errors";
import { israelToday } from "../documents/helpers";
import { lineOk, type PurchaseLine } from "./purchaseLines";
import { PurchaseLinesEditor } from "./PurchaseLinesEditor";
import { SupplierPicker } from "./SupplierPicker";

const EMPTY_LINE: PurchaseLine = { item_id: null, description: "", quantity: "1", unit_cost: "" };

/** What still has to arrive on the order's product lines. */
function remaining(order: PurchaseOrder, items: Item[]): PurchaseLine[] {
  const products = new Set(items.filter((i) => i.item_type === "product").map((i) => i.id));
  return order.lines
    .filter((l) => l.item_id && products.has(l.item_id))
    .map((l) => ({
      item_id: l.item_id,
      order_line_id: l.id,
      description: l.description,
      quantity: String(Math.max(Number(l.quantity) - Number(l.received_quantity), 0)),
      unit_cost: String(Number(l.unit_cost)),
    }))
    .filter((l) => Number(l.quantity) > 0);
}

/** Goods that arrived, from an order or without one. Saved receipts cannot be changed. */
export function ReceiptDialog({
  businessId,
  order,
  onClose,
}: {
  businessId: string;
  order: PurchaseOrder | null;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const fullScreen = useMediaQuery(useTheme().breakpoints.down("md"));
  const queryClient = useQueryClient();
  const items = useQuery({
    queryKey: ["business", businessId, "items", ""],
    queryFn: () => api.get<Item[]>(`/businesses/${businessId}/items?limit=200&q=`),
  });
  const [supplierId, setSupplierId] = useState(order?.supplier.id ?? "");
  const [date, setDate] = useState(israelToday());
  const [reference, setReference] = useState("");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<PurchaseLine[] | null>(order ? null : [EMPTY_LINE]);
  const [touched, setTouched] = useState(false);
  const shown = lines ?? (order && items.data ? remaining(order, items.data) : []);

  const save = useMutation({
    mutationFn: () =>
      api.post<GoodsReceipt>(`/businesses/${businessId}/goods-receipts`, {
        supplier_id: supplierId,
        purchase_order_id: order?.id ?? null,
        receipt_date: date,
        supplier_reference: reference.trim(),
        notes,
        lines: shown
          .filter((l) => Number(l.quantity) > 0)
          .map((l) => ({
            item_id: l.item_id,
            order_line_id: l.order_line_id ?? null,
            quantity: finishAmount(l.quantity),
            unit_cost: finishAmount(l.unit_cost),
          })),
      }),
    onSuccess: async () => {
      for (const key of ["purchase-orders", "goods-receipts", "inventory"]) {
        await queryClient.invalidateQueries({ queryKey: ["business", businessId, key] });
      }
      onClose();
    },
  });
  const ok =
    supplierId !== "" &&
    date !== "" &&
    shown.some((l) => Number(l.quantity) > 0) &&
    shown.filter((l) => Number(l.quantity) > 0).every((l) => lineOk(l, true));
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (ok) save.mutate();
  };

  return (
    <Dialog open onClose={onClose} fullScreen={fullScreen} maxWidth="md" fullWidth>
      <form onSubmit={submit} noValidate>
        <DialogTitle>
          {order ? t("receipts.fromOrder", { number: order.number }) : t("receipts.new")}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={3} sx={{ pt: 1 }}>
            {save.isError && <Alert severity="error">{errorMessage(t, save.error)}</Alert>}
            <Typography variant="body2" color="text.secondary">
              {t("receipts.help")}
            </Typography>
            <Grid container spacing={2}>
              <Grid size={{ xs: 12, sm: 6 }}>
                <SupplierPicker
                  businessId={businessId}
                  value={supplierId}
                  onChange={setSupplierId}
                  disabled={Boolean(order)}
                  error={touched && !supplierId}
                />
              </Grid>
              <Grid size={{ xs: 6, sm: 3 }}>
                <TextField
                  type="date"
                  label={t("receipts.date")}
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                  fullWidth
                  required
                  slotProps={{ inputLabel: { shrink: true } }}
                />
              </Grid>
              <Grid size={{ xs: 6, sm: 3 }}>
                <TextField
                  label={t("receipts.reference")}
                  value={reference}
                  onChange={(e) => setReference(e.target.value)}
                  fullWidth
                />
              </Grid>
            </Grid>
            {order && items.data && shown.length === 0 && (
              <Alert severity="info">{t("receipts.nothingLeft")}</Alert>
            )}
            {(!order || shown.length > 0) && (
              <PurchaseLinesEditor
                businessId={businessId}
                lines={shown}
                onChange={setLines}
                productsOnly
                error={touched}
              />
            )}
            <TextField
              label={t("purchasing.notes")}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              multiline
              minRows={2}
            />
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={onClose}>{t("common.cancel")}</Button>
          <Button type="submit" variant="contained" disabled={save.isPending}>
            {t("receipts.save")}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
