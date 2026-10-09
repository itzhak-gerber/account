import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Link from "@mui/material/Link";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link as RouterLink } from "react-router";

import { api } from "../../api/client";
import type { Item, StockMovement } from "../../api/types";
import { formatMoney } from "../../lib/money";

const qty = (value: string) => Number(value).toLocaleString("he-IL");

/** The ledger of one product: every sale, return and adjustment, newest first. */
export function MovementsDialog({
  businessId,
  item,
  onClose,
}: {
  businessId: string;
  item: Item;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const movements = useQuery({
    queryKey: ["business", businessId, "inventory", item.id, "movements"],
    queryFn: () =>
      api.get<StockMovement[]>(`/businesses/${businessId}/inventory/${item.id}/movements`),
  });
  const label = t("inventory.historyOf", { name: item.name });

  return (
    <Dialog open onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>{label}</DialogTitle>
      <DialogContent>
        {movements.data?.length === 0 && (
          <Typography color="text.secondary">{t("inventory.noMovements")}</Typography>
        )}
        {movements.data && movements.data.length > 0 && (
          <TableContainer tabIndex={0} role="region" aria-label={label}>
            <Table size="small" aria-label={label}>
              <TableHead>
                <TableRow>
                  <TableCell>{t("inventory.when")}</TableCell>
                  <TableCell>{t("inventory.kind")}</TableCell>
                  <TableCell align="left">{t("inventory.change")}</TableCell>
                  <TableCell align="left">{t("inventory.balance")}</TableCell>
                  <TableCell align="left">{t("inventory.cost")}</TableCell>
                  <TableCell>{t("inventory.details")}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {movements.data.map((m) => (
                  <TableRow key={m.id}>
                    <TableCell>{new Date(m.created_at).toLocaleString("he-IL")}</TableCell>
                    <TableCell>{t(`inventory.kinds.${m.kind}`)}</TableCell>
                    <TableCell align="left" dir="ltr">
                      {Number(m.quantity) > 0 ? "+" : ""}
                      {qty(m.quantity)}
                    </TableCell>
                    <TableCell align="left">{qty(m.balance_after)}</TableCell>
                    <TableCell align="left">{formatMoney(m.unit_cost)}</TableCell>
                    <TableCell>
                      {m.document_id ? (
                        <Link component={RouterLink} to={`/documents/${m.document_id}`}>
                          {m.kit_item_id ? t("inventory.viaKit") : t("inventory.document")}
                        </Link>
                      ) : (
                        m.reason
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t("inventory.close")}</Button>
      </DialogActions>
    </Dialog>
  );
}
