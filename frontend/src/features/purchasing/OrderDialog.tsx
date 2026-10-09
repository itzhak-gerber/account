import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Grid from "@mui/material/Grid";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { PurchaseOrder } from "../../api/types";
import { finishAmount } from "../../lib/amount";
import { errorMessage } from "../../lib/errors";
import { israelToday } from "../documents/helpers";
import { lineOk, type PurchaseLine } from "./purchaseLines";
import { PurchaseLinesEditor } from "./PurchaseLinesEditor";
import { SupplierPicker } from "./SupplierPicker";

const qtyText = (value: string) => String(Number(value));

/** A new purchase order, or changes to one that nothing has arrived for yet. */
export function OrderDialog({
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
  const [supplierId, setSupplierId] = useState(order?.supplier.id ?? "");
  const [orderDate, setOrderDate] = useState(order?.order_date ?? israelToday());
  const [expected, setExpected] = useState(order?.expected_date ?? "");
  const [notes, setNotes] = useState(order?.notes ?? "");
  const [lines, setLines] = useState<PurchaseLine[]>(
    order
      ? order.lines.map((l) => ({
          item_id: l.item_id,
          description: l.description,
          quantity: qtyText(l.quantity),
          unit_cost: qtyText(l.unit_cost),
        }))
      : [{ item_id: null, description: "", quantity: "1", unit_cost: "" }],
  );
  const [touched, setTouched] = useState(false);
  const base = `/businesses/${businessId}/purchase-orders`;

  const save = useMutation({
    mutationFn: () => {
      const body = {
        supplier_id: supplierId,
        order_date: orderDate,
        expected_date: expected || null,
        notes,
        lines: lines.map((l) => ({
          item_id: l.item_id,
          description: l.description.trim(),
          quantity: finishAmount(l.quantity),
          unit_cost: finishAmount(l.unit_cost),
        })),
      };
      return order
        ? api.patch<PurchaseOrder>(`${base}/${order.id}`, body)
        : api.post<PurchaseOrder>(base, body);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["business", businessId, "purchase-orders"],
      });
      onClose();
    },
  });
  const ok = supplierId !== "" && orderDate !== "" && lines.every((l) => lineOk(l, false));
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (ok) save.mutate();
  };

  return (
    <Dialog open onClose={onClose} fullScreen={fullScreen} maxWidth="md" fullWidth>
      <form onSubmit={submit} noValidate>
        <DialogTitle>
          {order ? t("orders.editTitle", { number: order.number }) : t("orders.new")}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={3} sx={{ pt: 1 }}>
            {save.isError && <Alert severity="error">{errorMessage(t, save.error)}</Alert>}
            <Grid container spacing={2}>
              <Grid size={{ xs: 12, sm: 6 }}>
                <SupplierPicker
                  businessId={businessId}
                  value={supplierId}
                  onChange={setSupplierId}
                  error={touched && !supplierId}
                />
              </Grid>
              <Grid size={{ xs: 6, sm: 3 }}>
                <TextField
                  type="date"
                  label={t("orders.orderDate")}
                  value={orderDate}
                  onChange={(e) => setOrderDate(e.target.value)}
                  fullWidth
                  required
                  slotProps={{ inputLabel: { shrink: true } }}
                />
              </Grid>
              <Grid size={{ xs: 6, sm: 3 }}>
                <TextField
                  type="date"
                  label={t("orders.expectedDate")}
                  value={expected}
                  onChange={(e) => setExpected(e.target.value)}
                  fullWidth
                  slotProps={{ inputLabel: { shrink: true } }}
                />
              </Grid>
            </Grid>
            <PurchaseLinesEditor
              businessId={businessId}
              lines={lines}
              onChange={setLines}
              productsOnly={false}
              error={touched}
            />
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
            {t("purchasing.save")}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
