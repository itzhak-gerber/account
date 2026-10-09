import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControlLabel from "@mui/material/FormControlLabel";
import FormGroup from "@mui/material/FormGroup";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import { api } from "../../api/client";
import type { DocumentSummary, DocumentType, InvoiceDocument } from "../../api/types";
import { errorMessage } from "../../lib/errors";
import { formatDate, formatMoney } from "../../lib/money";

/** One invoice for several delivery notes of a customer (חשבונית מרכזת). */
export function InvoiceDeliveryNotesDialog({
  businessId,
  onClose,
}: {
  businessId: string;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const notes = useQuery({
    queryKey: ["business", businessId, "documents", "uninvoiced"],
    queryFn: () =>
      api.get<DocumentSummary[]>(`/businesses/${businessId}/documents?uninvoiced=true&limit=200`),
  });
  const customers = [...new Set((notes.data ?? []).map((n) => n.customer_name))].sort();
  const [customer, setCustomer] = useState<string | null>(null);
  const [unchecked, setUnchecked] = useState<Set<string>>(new Set());
  const [type, setType] = useState<DocumentType>("tax_invoice");
  const chosen = customer ?? customers[0] ?? "";
  const forCustomer = (notes.data ?? [])
    .filter((n) => n.customer_name === chosen)
    .sort((a, b) => a.issue_date.localeCompare(b.issue_date) || (a.number ?? 0) - (b.number ?? 0));
  const selected = forCustomer.filter((n) => !unchecked.has(n.id));

  const create = useMutation({
    mutationFn: () =>
      api.post<InvoiceDocument>(`/businesses/${businessId}/documents/invoice-delivery-notes`, {
        delivery_note_ids: selected.map((n) => n.id),
        type,
      }),
    onSuccess: async (draft) => {
      await queryClient.invalidateQueries({ queryKey: ["business", businessId] });
      void navigate(`/documents/${draft.id}`);
    },
  });
  const toggle = (id: string) =>
    setUnchecked((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t("deliveryNotes.consolidateTitle")}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          {create.isError && <Alert severity="error">{errorMessage(t, create.error)}</Alert>}
          <Typography variant="body2" color="text.secondary">
            {t("deliveryNotes.consolidateHelp")}
          </Typography>
          {notes.data?.length === 0 && <Alert severity="info">{t("deliveryNotes.noneOpen")}</Alert>}
          {customers.length > 0 && (
            <TextField
              select
              label={t("deliveryNotes.customer")}
              value={chosen}
              onChange={(e) => {
                setCustomer(e.target.value);
                setUnchecked(new Set());
              }}
            >
              {customers.map((name) => (
                <MenuItem key={name} value={name}>
                  {name || "—"}
                </MenuItem>
              ))}
            </TextField>
          )}
          {forCustomer.length > 0 && (
            <FormGroup aria-label={t("deliveryNotes.notes")}>
              {forCustomer.map((n) => (
                <FormControlLabel
                  key={n.id}
                  control={
                    <Checkbox checked={!unchecked.has(n.id)} onChange={() => toggle(n.id)} />
                  }
                  label={`${t("docTypes.delivery_note")} ${n.number} · ${formatDate(n.issue_date)} · ${formatMoney(n.total)}`}
                />
              ))}
            </FormGroup>
          )}
          {forCustomer.length > 0 && (
            <TextField
              select
              label={t("deliveryNotes.invoiceType")}
              value={type}
              onChange={(e) => setType(e.target.value as DocumentType)}
            >
              <MenuItem value="tax_invoice">{t("docTypes.tax_invoice")}</MenuItem>
              <MenuItem value="tax_invoice_receipt">{t("docTypes.tax_invoice_receipt")}</MenuItem>
            </TextField>
          )}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose}>{t("common.cancel")}</Button>
        <Button
          variant="contained"
          disabled={selected.length === 0 || create.isPending}
          onClick={() => create.mutate()}
        >
          {t("deliveryNotes.createInvoice", { count: selected.length })}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
