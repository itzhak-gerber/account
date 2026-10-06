import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControlLabel from "@mui/material/FormControlLabel";
import Grid from "@mui/material/Grid";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import { api } from "../../api/client";
import type {
  CustomerDetails,
  DocumentType,
  DocumentTypeInfo,
  InvoiceDocument,
  LineInput,
  PaymentInput,
} from "../../api/types";
import { useSession } from "../../auth/context";
import { can } from "../../auth/permissions";
import { errorMessage } from "../../lib/errors";
import { formatDate, formatMoney, previewTotals } from "../../lib/money";
import { AllocationsEditor } from "./AllocationsEditor";
import { CustomerPicker } from "./CustomerPicker";
import { pdfUrl } from "./hooks";
import { EMPTY_LINE, israelToday, type AllocationRow } from "./helpers";
import { LinesEditor } from "./LinesEditor";
import { PaymentsEditor } from "./PaymentsEditor";

const EMPTY_CUSTOMER: CustomerDetails = {
  name: "",
  tax_id: "",
  email: null,
  phone: "",
  address_street: "",
  address_city: "",
  address_zip: "",
};

interface EditorState {
  issue_date: string;
  due_date: string | null;
  customer_id: string | null;
  customer: CustomerDetails;
  prices_include_vat: boolean;
  lines: LineInput[];
  payments: PaymentInput[];
  allocations: AllocationRow[];
  notes: string;
}

function allocationLabel(
  t: (key: string) => string,
  a: { invoice_type: string; invoice_number: number | null; invoice_date: string },
) {
  return `${t(`docTypes.${a.invoice_type}`)} ${t("documents.number")} ${a.invoice_number} · ${formatDate(a.invoice_date)}`;
}

function stateFrom(
  doc: InvoiceDocument | null,
  info: DocumentTypeInfo,
  t: (key: string) => string,
  payInvoice?: InvoiceDocument | null,
): EditorState {
  if (!doc && payInvoice) {
    // A receipt started from an unpaid invoice: same customer, that invoice, its open balance.
    const balance = payInvoice.balance_due ?? payInvoice.total;
    return {
      issue_date: israelToday(),
      due_date: null,
      customer_id: payInvoice.customer_id,
      customer: { ...EMPTY_CUSTOMER, ...payInvoice.customer },
      prices_include_vat: false,
      lines: [],
      payments: [
        { method: "bank_transfer", amount: balance, payment_date: israelToday(), details: {} },
      ],
      allocations: [
        {
          invoice_id: payInvoice.id,
          amount: balance,
          balance,
          label: allocationLabel(t, {
            invoice_type: payInvoice.type,
            invoice_number: payInvoice.number,
            invoice_date: payInvoice.issue_date,
          }),
        },
      ],
      notes: "",
    };
  }
  if (!doc) {
    return {
      issue_date: israelToday(),
      due_date: null,
      customer_id: null,
      customer: EMPTY_CUSTOMER,
      prices_include_vat: false,
      lines: info.has_lines ? [{ ...EMPTY_LINE }] : [],
      payments: [],
      allocations: [],
      notes: "",
    };
  }
  return {
    issue_date: doc.issue_date,
    due_date: doc.due_date,
    customer_id: doc.customer_id,
    customer: { ...EMPTY_CUSTOMER, ...doc.customer },
    prices_include_vat: doc.prices_include_vat,
    lines: doc.lines.map((l) => ({
      item_id: l.item_id,
      description: l.description,
      quantity: String(Number(l.quantity)),
      unit_of_measure: l.unit_of_measure,
      unit_price: l.unit_price,
      discount_percent: String(Number(l.discount_percent)),
      vat_type: l.vat_type,
    })),
    payments: doc.payments.map((p) => ({
      method: p.method,
      amount: p.amount,
      payment_date: p.payment_date,
      details: p.details,
    })),
    allocations: doc.allocations.map((a) => ({
      invoice_id: a.invoice_id,
      amount: a.amount,
      balance: a.balance_due,
      label: allocationLabel(t, a),
    })),
    notes: doc.notes,
  };
}

function toPayload(state: EditorState) {
  return {
    ...state,
    customer: { ...state.customer, email: state.customer.email?.trim() || null },
    lines: state.lines
      .filter((l) => l.description.trim())
      .map((l) => ({
        ...l,
        quantity: l.quantity || "1",
        unit_price: l.unit_price || "0",
        discount_percent: l.discount_percent || "0",
      })),
    payments: state.payments.filter((p) => Number(p.amount) > 0),
    allocations: state.allocations.map((a) => ({ invoice_id: a.invoice_id, amount: a.amount })),
  };
}

interface Props {
  businessId: string;
  type: DocumentType;
  info: DocumentTypeInfo;
  document: InvoiceDocument | null;
  payInvoice?: InvoiceDocument | null;
}

export function DocumentEditor({ businessId, type, info, document, payInvoice }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { current } = useSession();
  const [state, setState] = useState<EditorState>(() => stateFrom(document, info, t, payInvoice));
  const [docId, setDocId] = useState<string | null>(document?.id ?? null);
  const [confirmIssue, setConfirmIssue] = useState(false);
  const base = `/businesses/${businessId}/documents`;

  const businessType = current!.business.business_type;
  const vatRegistered = businessType === "licensed_dealer" || businessType === "company";
  const showVat = info.shows_vat && vatRegistered;
  const vatRate =
    document && Number(document.vat_rate) > 0 ? Number(document.vat_rate) : showVat ? 0.18 : 0;
  const totals = previewTotals(state.lines, vatRate, state.prices_include_vat && showVat);
  const total = info.has_lines
    ? totals.total
    : state.payments.reduce((s, p) => s + Number(p.amount || 0), 0);
  const paid = state.payments.reduce((s, p) => s + Number(p.amount || 0), 0);
  const creditOf = document?.related.find((r) => r.relation === "credits");

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["business", businessId] });
  const save = useMutation({
    mutationFn: async () => {
      const payload = toPayload(state);
      if (docId) return api.patch<InvoiceDocument>(`${base}/${docId}`, payload);
      const created = await api.post<InvoiceDocument>(base, { type, ...payload });
      setDocId(created.id);
      void navigate(`/documents/${created.id}`, { replace: true });
      return created;
    },
    onSuccess: invalidate,
  });
  const issue = useMutation({
    mutationFn: async () => {
      const saved = await save.mutateAsync();
      return api.post<InvoiceDocument>(`${base}/${saved.id}/issue`);
    },
    onSuccess: async (issued) => {
      setConfirmIssue(false);
      await invalidate();
      void navigate(`/documents/${issued.id}`, { replace: true });
    },
    onError: () => setConfirmIssue(false),
  });
  const remove = useMutation({
    mutationFn: () => api.delete(`${base}/${docId}`),
    onSuccess: async () => {
      await invalidate();
      void navigate("/documents");
    },
  });
  const preview = async () => {
    const saved = await save.mutateAsync();
    window.open(pdfUrl(businessId, saved.id), "_blank", "noopener");
  };

  const error = issue.error ?? save.error ?? remove.error;
  const busy = save.isPending || issue.isPending;
  const canEdit = can(current?.role, "editDocuments");

  return (
    <Stack spacing={3} sx={{ maxWidth: 1100 }}>
      <Stack direction="row" spacing={2} sx={{ alignItems: "center", flexWrap: "wrap" }}>
        <Typography variant="h4" component="h1" sx={{ fontWeight: 700 }}>
          {info.title}
        </Typography>
        <Chip label={t("docStatus.draft")} />
      </Stack>
      {creditOf && (
        <Typography color="text.secondary">
          {t("editor.creditFor", { type: t(`docTypes.${creditOf.type}`), number: creditOf.number })}
        </Typography>
      )}
      {error && <Alert severity="error">{errorMessage(t, error)}</Alert>}
      {save.isSuccess && !error && !issue.isPending && (
        <Alert severity="success">{t("editor.saved")}</Alert>
      )}

      <Card variant="outlined">
        <CardContent>
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, md: 6 }}>
              <CustomerPicker
                businessId={businessId}
                customerId={state.customer_id}
                details={state.customer}
                canSaveCustomer={can(current?.role, "manageCatalog")}
                onChange={(customer_id, customer) =>
                  setState((s) => ({ ...s, customer_id, customer }))
                }
              />
            </Grid>
            <Grid size={{ xs: 6, md: 3 }}>
              <TextField
                type="date"
                fullWidth
                label={t("editor.issueDate")}
                value={state.issue_date}
                onChange={(e) => setState((s) => ({ ...s, issue_date: e.target.value }))}
                slotProps={{ inputLabel: { shrink: true }, htmlInput: { max: israelToday() } }}
              />
            </Grid>
            {info.has_due_date && (
              <Grid size={{ xs: 6, md: 3 }}>
                <TextField
                  type="date"
                  fullWidth
                  label={t("editor.dueDate")}
                  value={state.due_date ?? ""}
                  onChange={(e) => setState((s) => ({ ...s, due_date: e.target.value || null }))}
                  slotProps={{ inputLabel: { shrink: true } }}
                />
              </Grid>
            )}
          </Grid>
        </CardContent>
      </Card>

      {info.has_lines && (
        <Box>
          <Stack
            direction="row"
            sx={{ justifyContent: "space-between", alignItems: "center", mb: 1 }}
          >
            <Typography variant="h6" component="h2">
              {t("editor.lines")}
            </Typography>
            {showVat && (
              <FormControlLabel
                control={
                  <Switch
                    checked={state.prices_include_vat}
                    onChange={(e) =>
                      setState((s) => ({ ...s, prices_include_vat: e.target.checked }))
                    }
                  />
                }
                label={t("editor.pricesIncludeVat")}
              />
            )}
          </Stack>
          <LinesEditor
            businessId={businessId}
            lines={state.lines}
            lineTotals={totals.lineTotals}
            showVat={showVat}
            pricesIncludeVat={state.prices_include_vat && showVat}
            onChange={(lines) => setState((s) => ({ ...s, lines }))}
          />
        </Box>
      )}

      {type === "receipt" && (
        <AllocationsEditor
          businessId={businessId}
          customerId={state.customer_id}
          rows={state.allocations}
          paymentsTotal={paid}
          onChange={(allocations) => setState((s) => ({ ...s, allocations }))}
          onFillPayment={(amount) =>
            setState((s) => ({
              ...s,
              payments:
                s.payments.length === 0
                  ? [
                      {
                        method: "bank_transfer",
                        amount: amount.toFixed(2),
                        payment_date: s.issue_date,
                        details: {},
                      },
                    ]
                  : s.payments.map((p, i) => (i === 0 ? { ...p, amount: amount.toFixed(2) } : p)),
            }))
          }
        />
      )}

      {info.has_payments && (
        <Box>
          <Typography variant="h6" component="h2" sx={{ mb: 1 }}>
            {t("editor.payments")}
          </Typography>
          <PaymentsEditor
            payments={state.payments}
            defaultDate={state.issue_date}
            remaining={info.has_lines ? total - paid : 0}
            onChange={(payments) => setState((s) => ({ ...s, payments }))}
          />
        </Box>
      )}

      <TextField
        label={t("editor.notes")}
        multiline
        minRows={2}
        value={state.notes}
        onChange={(e) => setState((s) => ({ ...s, notes: e.target.value }))}
      />

      <Card variant="outlined" sx={{ alignSelf: { md: "flex-end" }, minWidth: { md: 360 } }}>
        <CardContent>
          {showVat && info.has_lines && (
            <>
              <Row label={t("editor.subtotal")} value={formatMoney(totals.subtotal)} />
              <Row
                label={t("editor.vatAmount", { rate: Math.round(vatRate * 1000) / 10 })}
                value={formatMoney(totals.vat)}
              />
            </>
          )}
          <Row label={t("editor.total")} value={formatMoney(total)} strong />
          {info.has_payments && info.has_lines && (
            <>
              <Row label={t("editor.paid")} value={formatMoney(paid)} />
              <Row label={t("editor.remaining")} value={formatMoney(total - paid)} />
            </>
          )}
          <Typography variant="caption" color="text.secondary">
            {t("editor.previewNote")}
          </Typography>
        </CardContent>
      </Card>

      {canEdit && (
        <Stack
          direction={{ xs: "column", sm: "row" }}
          spacing={2}
          sx={{ justifyContent: "flex-end" }}
        >
          {docId && (
            <Button
              color="error"
              disabled={busy}
              onClick={() => window.confirm(t("editor.confirmDelete")) && remove.mutate()}
            >
              {t("editor.deleteDraft")}
            </Button>
          )}
          <Button variant="outlined" disabled={busy} onClick={() => void preview()}>
            {t("editor.preview")}
          </Button>
          <Button variant="outlined" disabled={busy} onClick={() => save.mutate()}>
            {t("editor.saveDraft")}
          </Button>
          <Button
            variant="contained"
            size="large"
            disabled={busy}
            onClick={() => setConfirmIssue(true)}
          >
            {t("editor.issue")}
          </Button>
        </Stack>
      )}

      <Dialog open={confirmIssue} onClose={() => setConfirmIssue(false)}>
        <DialogTitle>{t("editor.confirmIssueTitle")}</DialogTitle>
        <DialogContent>
          <Typography sx={{ mb: 1 }}>
            {info.title} · {state.customer.name || "—"} · <strong>{formatMoney(total)}</strong>
          </Typography>
          <Typography color="text.secondary">{t("editor.confirmIssueBody")}</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmIssue(false)}>{t("common.cancel")}</Button>
          <Button variant="contained" disabled={issue.isPending} onClick={() => issue.mutate()}>
            {t("editor.issue")}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}

function Row({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <Stack direction="row" sx={{ justifyContent: "space-between", py: 0.5, gap: 4 }}>
      <Typography sx={{ fontWeight: strong ? 700 : 400 }}>{label}</Typography>
      <Typography sx={{ fontWeight: strong ? 700 : 400, fontSize: strong ? "1.15rem" : undefined }}>
        {value}
      </Typography>
    </Stack>
  );
}
