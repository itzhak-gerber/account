import AddIcon from "@mui/icons-material/Add";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { OrderStatus, PurchaseOrder } from "../../api/types";
import { errorMessage } from "../../lib/errors";
import { formatDate, formatMoney } from "../../lib/money";
import { OrderDialog } from "./OrderDialog";
import { ReceiptDialog } from "./ReceiptDialog";

const STATUS_COLOR: Record<OrderStatus, "info" | "warning" | "success" | "default"> = {
  open: "info",
  partial: "warning",
  received: "success",
  cancelled: "default",
};
const qty = (value: string) => Number(value).toLocaleString("he-IL");

export function OrdersTab({ businessId, canEdit }: { businessId: string; canEdit: boolean }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<PurchaseOrder | null | "new">(null);
  const [viewing, setViewing] = useState<PurchaseOrder | null>(null);
  const [receiving, setReceiving] = useState<PurchaseOrder | null>(null);
  const orders = useQuery({
    queryKey: ["business", businessId, "purchase-orders"],
    queryFn: () => api.get<PurchaseOrder[]>(`/businesses/${businessId}/purchase-orders`),
  });
  const cancel = useMutation({
    mutationFn: (order: PurchaseOrder) =>
      api.post<PurchaseOrder>(`/businesses/${businessId}/purchase-orders/${order.id}/cancel`),
    onSuccess: async () => {
      setViewing(null);
      await queryClient.invalidateQueries({
        queryKey: ["business", businessId, "purchase-orders"],
      });
    },
  });
  const active = (o: PurchaseOrder) => o.status === "open" || o.status === "partial";

  return (
    <Stack spacing={2}>
      {canEdit && (
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => setEditing("new")}
          sx={{ alignSelf: "flex-start" }}
        >
          {t("orders.new")}
        </Button>
      )}
      <Card variant="outlined">
        {orders.data?.length === 0 && (
          <Typography sx={{ p: 2 }} color="text.secondary">
            {t("orders.empty")}
          </Typography>
        )}
        {orders.data && orders.data.length > 0 && (
          <TableContainer tabIndex={0} role="region" aria-label={t("orders.title")}>
            <Table size="small" aria-label={t("orders.title")}>
              <TableHead>
                <TableRow>
                  <TableCell>{t("orders.number")}</TableCell>
                  <TableCell>{t("purchasing.supplier")}</TableCell>
                  <TableCell>{t("orders.orderDate")}</TableCell>
                  <TableCell align="left">{t("purchasing.totalBeforeVat")}</TableCell>
                  <TableCell>{t("orders.status")}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {orders.data.map((o) => (
                  <TableRow key={o.id} hover>
                    <TableCell>
                      <Button size="small" onClick={() => setViewing(o)}>
                        {t("orders.open", { number: o.number })}
                      </Button>
                    </TableCell>
                    <TableCell>{o.supplier.name}</TableCell>
                    <TableCell>{formatDate(o.order_date)}</TableCell>
                    <TableCell align="left">{formatMoney(o.total)}</TableCell>
                    <TableCell>
                      <Chip
                        size="small"
                        variant="outlined"
                        color={STATUS_COLOR[o.status]}
                        label={t(`orders.statuses.${o.status}`)}
                      />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Card>

      {viewing && (
        <Dialog open onClose={() => setViewing(null)} maxWidth="md" fullWidth>
          <DialogTitle>
            {t("orders.viewTitle", { number: viewing.number, supplier: viewing.supplier.name })}
          </DialogTitle>
          <DialogContent>
            {cancel.isError && (
              <Alert severity="error" sx={{ mb: 2 }}>
                {errorMessage(t, cancel.error)}
              </Alert>
            )}
            <Typography sx={{ mb: 1 }}>
              {t("orders.orderDate")}: {formatDate(viewing.order_date)}
              {viewing.expected_date &&
                ` · ${t("orders.expectedDate")}: ${formatDate(viewing.expected_date)}`}
            </Typography>
            <TableContainer tabIndex={0} role="region" aria-label={t("purchasing.lines")}>
              <Table size="small" aria-label={t("purchasing.lines")}>
                <TableHead>
                  <TableRow>
                    <TableCell>{t("purchasing.descriptionHeader")}</TableCell>
                    <TableCell align="left">{t("orders.ordered")}</TableCell>
                    <TableCell align="left">{t("orders.received")}</TableCell>
                    <TableCell align="left">{t("purchasing.unitCostHeader")}</TableCell>
                    <TableCell align="left">{t("purchasing.lineTotal")}</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {viewing.lines.map((l) => (
                    <TableRow key={l.id}>
                      <TableCell>{l.description}</TableCell>
                      <TableCell align="left">{qty(l.quantity)}</TableCell>
                      <TableCell align="left">
                        {l.item_id ? qty(l.received_quantity) : "—"}
                      </TableCell>
                      <TableCell align="left">{formatMoney(l.unit_cost)}</TableCell>
                      <TableCell align="left">{formatMoney(l.total)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
            <Typography sx={{ mt: 1, fontWeight: 600 }}>
              {t("purchasing.totalBeforeVat")}: {formatMoney(viewing.total)}
            </Typography>
            {viewing.notes && <Typography sx={{ mt: 1 }}>{viewing.notes}</Typography>}
          </DialogContent>
          <DialogActions sx={{ flexWrap: "wrap", gap: 1 }}>
            {canEdit && active(viewing) && (
              <Button
                color="error"
                disabled={cancel.isPending}
                onClick={() => cancel.mutate(viewing)}
              >
                {t("orders.cancelOrder")}
              </Button>
            )}
            {canEdit && viewing.status === "open" && (
              <Button
                onClick={() => {
                  setEditing(viewing);
                  setViewing(null);
                }}
              >
                {t("orders.edit")}
              </Button>
            )}
            {canEdit && active(viewing) && (
              <Button
                variant="contained"
                onClick={() => {
                  setReceiving(viewing);
                  setViewing(null);
                }}
              >
                {t("orders.receive")}
              </Button>
            )}
            <Button onClick={() => setViewing(null)}>{t("inventory.close")}</Button>
          </DialogActions>
        </Dialog>
      )}
      {editing !== null && (
        <OrderDialog
          businessId={businessId}
          order={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
        />
      )}
      {receiving && (
        <ReceiptDialog
          businessId={businessId}
          order={receiving}
          onClose={() => setReceiving(null)}
        />
      )}
    </Stack>
  );
}
