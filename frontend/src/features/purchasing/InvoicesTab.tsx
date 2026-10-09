import AddIcon from "@mui/icons-material/Add";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { SupplierInvoice } from "../../api/types";
import { formatDate, formatMoney } from "../../lib/money";
import { israelToday } from "../documents/helpers";
import { SupplierInvoiceDialog } from "./SupplierInvoiceDialog";

type Filter = "all" | "unpaid";

export function InvoicesTab({ businessId, canEdit }: { businessId: string; canEdit: boolean }) {
  const { t } = useTranslation();
  const [filter, setFilter] = useState<Filter>("unpaid");
  const [editing, setEditing] = useState<SupplierInvoice | null | "new">(null);
  const invoices = useQuery({
    queryKey: ["business", businessId, "supplier-invoices"],
    queryFn: () => api.get<SupplierInvoice[]>(`/businesses/${businessId}/supplier-invoices`),
  });
  const today = israelToday();
  const overdue = (i: SupplierInvoice) => !i.paid_date && i.due_date !== null && i.due_date < today;
  const unpaid = (invoices.data ?? []).filter((i) => !i.paid_date);
  const shown = filter === "unpaid" ? unpaid : (invoices.data ?? []);
  const sum = (rows: SupplierInvoice[]) => rows.reduce((s, i) => s + Number(i.total), 0);

  return (
    <Stack spacing={2}>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
        <Card variant="outlined" sx={{ flex: 1 }}>
          <CardContent>
            <Typography color="text.secondary">{t("supplierInvoices.openBalance")}</Typography>
            <Typography variant="h5" component="p" sx={{ fontWeight: 700 }}>
              {formatMoney(sum(unpaid))}
            </Typography>
          </CardContent>
        </Card>
        <Card variant="outlined" sx={{ flex: 1 }}>
          <CardContent>
            <Typography color="text.secondary">{t("supplierInvoices.overdue")}</Typography>
            <Typography variant="h5" component="p" sx={{ fontWeight: 700 }}>
              {formatMoney(sum(unpaid.filter(overdue)))}
            </Typography>
          </CardContent>
        </Card>
      </Stack>
      <Stack direction="row" spacing={2} sx={{ alignItems: "center", flexWrap: "wrap", gap: 1 }}>
        {canEdit && (
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => setEditing("new")}>
            {t("supplierInvoices.new")}
          </Button>
        )}
        <ToggleButtonGroup
          size="small"
          exclusive
          value={filter}
          onChange={(_, v: Filter | null) => v && setFilter(v)}
          aria-label={t("supplierInvoices.filter")}
        >
          <ToggleButton value="unpaid">{t("supplierInvoices.unpaidOnly")}</ToggleButton>
          <ToggleButton value="all">{t("supplierInvoices.all")}</ToggleButton>
        </ToggleButtonGroup>
      </Stack>
      <Card variant="outlined">
        {invoices.data && shown.length === 0 && (
          <Typography sx={{ p: 2 }} color="text.secondary">
            {filter === "unpaid" ? t("supplierInvoices.noneOpen") : t("supplierInvoices.empty")}
          </Typography>
        )}
        {shown.length > 0 && (
          <TableContainer tabIndex={0} role="region" aria-label={t("supplierInvoices.title")}>
            <Table size="small" aria-label={t("supplierInvoices.title")}>
              <TableHead>
                <TableRow>
                  <TableCell>{t("purchasing.supplier")}</TableCell>
                  <TableCell>{t("supplierInvoices.number")}</TableCell>
                  <TableCell>{t("supplierInvoices.date")}</TableCell>
                  <TableCell>{t("supplierInvoices.dueDate")}</TableCell>
                  <TableCell align="left">{t("supplierInvoices.total")}</TableCell>
                  <TableCell>{t("supplierInvoices.status")}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {shown.map((i) => (
                  <TableRow key={i.id} hover>
                    <TableCell>{i.supplier.name}</TableCell>
                    <TableCell>
                      {canEdit ? (
                        <Button size="small" onClick={() => setEditing(i)}>
                          {i.invoice_number}
                        </Button>
                      ) : (
                        i.invoice_number
                      )}
                    </TableCell>
                    <TableCell>{formatDate(i.invoice_date)}</TableCell>
                    <TableCell>{i.due_date ? formatDate(i.due_date) : "—"}</TableCell>
                    <TableCell align="left">{formatMoney(i.total)}</TableCell>
                    <TableCell>
                      {i.paid_date ? (
                        <Chip
                          size="small"
                          color="success"
                          variant="outlined"
                          label={t("supplierInvoices.paidOn", { date: formatDate(i.paid_date) })}
                        />
                      ) : (
                        <Chip
                          size="small"
                          color={overdue(i) ? "error" : "warning"}
                          variant="outlined"
                          label={
                            overdue(i) ? t("supplierInvoices.late") : t("supplierInvoices.unpaid")
                          }
                        />
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Card>
      {editing !== null && (
        <SupplierInvoiceDialog
          businessId={businessId}
          invoice={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
        />
      )}
    </Stack>
  );
}
