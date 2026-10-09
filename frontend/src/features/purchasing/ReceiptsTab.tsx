import AddIcon from "@mui/icons-material/Add";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
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
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { GoodsReceipt } from "../../api/types";
import { formatDate, formatMoney } from "../../lib/money";
import { ReceiptDialog } from "./ReceiptDialog";

const qty = (value: string) => Number(value).toLocaleString("he-IL");

export function ReceiptsTab({ businessId, canEdit }: { businessId: string; canEdit: boolean }) {
  const { t } = useTranslation();
  const [creating, setCreating] = useState(false);
  const [viewing, setViewing] = useState<GoodsReceipt | null>(null);
  const receipts = useQuery({
    queryKey: ["business", businessId, "goods-receipts"],
    queryFn: () => api.get<GoodsReceipt[]>(`/businesses/${businessId}/goods-receipts`),
  });

  return (
    <Stack spacing={2}>
      {canEdit && (
        <Stack
          direction={{ xs: "column", sm: "row" }}
          spacing={2}
          sx={{ alignItems: { sm: "center" } }}
        >
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={() => setCreating(true)}
            sx={{ alignSelf: "flex-start" }}
          >
            {t("receipts.new")}
          </Button>
          <Typography variant="body2" color="text.secondary">
            {t("receipts.fromOrderHint")}
          </Typography>
        </Stack>
      )}
      <Card variant="outlined">
        {receipts.data?.length === 0 && (
          <Typography sx={{ p: 2 }} color="text.secondary">
            {t("receipts.empty")}
          </Typography>
        )}
        {receipts.data && receipts.data.length > 0 && (
          <TableContainer tabIndex={0} role="region" aria-label={t("receipts.title")}>
            <Table size="small" aria-label={t("receipts.title")}>
              <TableHead>
                <TableRow>
                  <TableCell>{t("receipts.number")}</TableCell>
                  <TableCell>{t("receipts.date")}</TableCell>
                  <TableCell>{t("purchasing.supplier")}</TableCell>
                  <TableCell>{t("receipts.reference")}</TableCell>
                  <TableCell align="left">{t("purchasing.totalBeforeVat")}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {receipts.data.map((r) => (
                  <TableRow key={r.id} hover>
                    <TableCell>
                      <Button size="small" onClick={() => setViewing(r)}>
                        {t("receipts.open", { number: r.number })}
                      </Button>
                    </TableCell>
                    <TableCell>{formatDate(r.receipt_date)}</TableCell>
                    <TableCell>{r.supplier.name}</TableCell>
                    <TableCell>{r.supplier_reference || "—"}</TableCell>
                    <TableCell align="left">{formatMoney(r.total)}</TableCell>
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
            {t("receipts.viewTitle", { number: viewing.number, supplier: viewing.supplier.name })}
          </DialogTitle>
          <DialogContent>
            <Typography sx={{ mb: 1 }}>
              {formatDate(viewing.receipt_date)}
              {viewing.supplier_reference &&
                ` · ${t("receipts.reference")}: ${viewing.supplier_reference}`}
            </Typography>
            <TableContainer tabIndex={0} role="region" aria-label={t("purchasing.lines")}>
              <Table size="small" aria-label={t("purchasing.lines")}>
                <TableHead>
                  <TableRow>
                    <TableCell>{t("purchasing.descriptionHeader")}</TableCell>
                    <TableCell align="left">{t("purchasing.quantityHeader")}</TableCell>
                    <TableCell align="left">{t("purchasing.unitCostHeader")}</TableCell>
                    <TableCell align="left">{t("purchasing.lineTotal")}</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {viewing.lines.map((l) => (
                    <TableRow key={l.id}>
                      <TableCell>{l.description}</TableCell>
                      <TableCell align="left">{qty(l.quantity)}</TableCell>
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
            <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
              {t("receipts.final")}
            </Typography>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setViewing(null)}>{t("inventory.close")}</Button>
          </DialogActions>
        </Dialog>
      )}
      {creating && (
        <ReceiptDialog businessId={businessId} order={null} onClose={() => setCreating(false)} />
      )}
    </Stack>
  );
}
