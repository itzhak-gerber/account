import MailOutlined from "@mui/icons-material/MailOutlined";
import PictureAsPdfOutlined from "@mui/icons-material/PictureAsPdfOutlined";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogTitle from "@mui/material/DialogTitle";
import Grid from "@mui/material/Grid";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link as RouterLink, useNavigate } from "react-router";

import { api } from "../../api/client";
import type { DocumentType, InvoiceDocument } from "../../api/types";
import { useSession } from "../../auth/context";
import { can } from "../../auth/permissions";
import { errorMessage } from "../../lib/errors";
import { formatDate, formatMoney } from "../../lib/money";
import { pdfUrl } from "./hooks";
import { DeliveryChip } from "./DeliveryChip";
import { PaymentChip } from "./PaymentChip";
import { SendEmailDialog } from "./SendEmailDialog";

const CONVERSIONS: Partial<Record<DocumentType, DocumentType[]>> = {
  quote: ["tax_invoice", "tax_invoice_receipt", "proforma_invoice"],
  proforma_invoice: ["tax_invoice", "tax_invoice_receipt"],
  delivery_note: ["tax_invoice", "tax_invoice_receipt"],
};

export function DocumentView({ businessId, doc }: { businessId: string; doc: InvoiceDocument }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { current } = useSession();
  const base = `/businesses/${businessId}/documents/${doc.id}`;
  const canEdit = can(current?.role, "editDocuments");
  const [emailing, setEmailing] = useState(false);
  const [confirmOriginal, setConfirmOriginal] = useState(false);
  const vatRegistered = ["licensed_dealer", "company"].includes(current!.business.business_type);

  const derive = useMutation({
    mutationFn: (target: DocumentType | "credit") =>
      target === "credit"
        ? api.post<InvoiceDocument>(`${base}/credit-note`)
        : api.post<InvoiceDocument>(`${base}/convert`, { type: target }),
    onSuccess: async (draft) => {
      await queryClient.invalidateQueries({ queryKey: ["business", businessId] });
      void navigate(`/documents/${draft.id}`);
    },
  });

  const askAgain = useMutation({
    mutationFn: () => api.post<InvoiceDocument>(`${base}/allocation`),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["business", businessId, "document", doc.id] }),
  });

  const refreshSoon = () =>
    setTimeout(
      () =>
        void queryClient.invalidateQueries({
          queryKey: ["business", businessId, "document", doc.id],
        }),
      1500,
    );
  const downloadOriginal = () => {
    setConfirmOriginal(false);
    window.open(pdfUrl(businessId, doc.id), "_blank", "noopener");
    refreshSoon();
  };

  const conversions = (
    doc.delivery_status === "invoiced" ? [] : (CONVERSIONS[doc.type] ?? [])
  ).filter((target) => vatRegistered || !["tax_invoice", "tax_invoice_receipt"].includes(target));
  const showVat = Number(doc.vat_rate) > 0;

  return (
    <Stack spacing={3} sx={{ maxWidth: 1000 }}>
      <Stack direction="row" spacing={2} sx={{ alignItems: "center", flexWrap: "wrap" }}>
        <Typography variant="h4" component="h1" sx={{ fontWeight: 700 }}>
          {doc.title} {t("documents.number")} {doc.number}
        </Typography>
        <Chip color="success" variant="outlined" label={t("docStatus.issued")} />
        {doc.payment_status && <PaymentChip status={doc.payment_status} />}
        {doc.delivery_status && <DeliveryChip status={doc.delivery_status} />}
      </Stack>
      {derive.isError && <Alert severity="error">{errorMessage(t, derive.error)}</Alert>}
      {doc.allocation_number && (
        <Typography>
          {t("allocation.number")}: <strong dir="ltr">{doc.allocation_number}</strong>
        </Typography>
      )}
      {(doc.allocation_status === "pending" || doc.allocation_status === "rejected") && (
        <Alert
          severity={doc.allocation_status === "pending" ? "warning" : "error"}
          action={
            canEdit && (
              <Button
                color="inherit"
                disabled={askAgain.isPending}
                onClick={() => askAgain.mutate()}
              >
                {t("allocation.askAgain")}
              </Button>
            )
          }
        >
          {t(`allocation.${doc.allocation_status}`)}
          {askAgain.isError && ` ${errorMessage(t, askAgain.error)}`}
        </Alert>
      )}

      <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
        <Button
          variant="contained"
          startIcon={<PictureAsPdfOutlined />}
          href={pdfUrl(businessId, doc.id)}
          target="_blank"
          rel="noopener"
          onClick={(e) => {
            // The first download is the legal original; say so before it is used up.
            if (!doc.original_delivered_at) {
              e.preventDefault();
              setConfirmOriginal(true);
            } else {
              refreshSoon();
            }
          }}
        >
          {t("view.downloadPdf")}
        </Button>
        {canEdit &&
          conversions.map((target) => (
            <Button
              key={target}
              variant="outlined"
              disabled={derive.isPending}
              onClick={() => derive.mutate(target)}
            >
              {t("view.convertTo", { type: t(`docTypes.${target}`) })}
            </Button>
          ))}
        {canEdit && (
          <Button variant="outlined" startIcon={<MailOutlined />} onClick={() => setEmailing(true)}>
            {t("email.send")}
          </Button>
        )}
        {canEdit &&
          doc.payment_status &&
          doc.payment_status !== "paid" &&
          doc.payment_status !== "superseded" &&
          ["tax_invoice", "proforma_invoice"].includes(doc.type) && (
            <Button
              variant="outlined"
              color="success"
              onClick={() => void navigate(`/documents/new?type=receipt&invoice=${doc.id}`)}
            >
              {t("view.issueReceipt")}
            </Button>
          )}
        {canEdit && ["tax_invoice", "tax_invoice_receipt"].includes(doc.type) && (
          <Button
            variant="outlined"
            color="warning"
            disabled={derive.isPending}
            onClick={() => derive.mutate("credit")}
          >
            {t("view.creditNote")}
          </Button>
        )}
      </Stack>
      <Typography variant="body2" color="text.secondary">
        {doc.original_delivered_at
          ? t("view.originalNote", {
              date: new Date(doc.original_delivered_at).toLocaleString("he-IL"),
            })
          : t("view.originalPending")}
      </Typography>

      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 6 }}>
          <Card variant="outlined" sx={{ height: "100%" }}>
            <CardContent>
              <Typography color="text.secondary" variant="body2">
                {t("view.customer")}
              </Typography>
              <Typography sx={{ fontWeight: 700 }}>{doc.customer.name}</Typography>
              {doc.customer.tax_id && (
                <Typography dir="ltr" sx={{ textAlign: "right" }}>
                  {doc.customer.tax_id}
                </Typography>
              )}
              <Typography>
                {[doc.customer.address_street, doc.customer.address_city]
                  .filter(Boolean)
                  .join(", ")}
              </Typography>
              {doc.customer.email && (
                <Typography dir="ltr" sx={{ textAlign: "right" }}>
                  {doc.customer.email}
                </Typography>
              )}
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Card variant="outlined" sx={{ height: "100%" }}>
            <CardContent>
              <Typography color="text.secondary" variant="body2">
                {t("view.dates")}
              </Typography>
              <Typography>
                {t("editor.issueDate")}: {formatDate(doc.issue_date)}
              </Typography>
              {doc.due_date && (
                <Typography>
                  {t("editor.dueDate")}: {formatDate(doc.due_date)}
                </Typography>
              )}
              {doc.issued_at && (
                <Typography variant="body2" color="text.secondary">
                  {t("view.issuedAt", { date: new Date(doc.issued_at).toLocaleString("he-IL") })}
                </Typography>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {doc.lines.length > 0 && (
        <TableContainer
          component={Card}
          variant="outlined"
          tabIndex={0}
          role="region"
          aria-label={t("view.lines")}
        >
          <Table size="small" aria-label={t("view.lines")}>
            <TableHead>
              <TableRow>
                <TableCell>{t("editor.description")}</TableCell>
                <TableCell align="left">{t("editor.quantity")}</TableCell>
                <TableCell align="left">{t("editor.unitPrice")}</TableCell>
                <TableCell align="left">{t("editor.discount")}</TableCell>
                <TableCell align="left">{t("editor.lineTotal")}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {doc.lines.map((l) => (
                <TableRow key={l.id}>
                  <TableCell>{l.description}</TableCell>
                  <TableCell align="left">
                    {Number(l.quantity)} {l.unit_of_measure}
                  </TableCell>
                  <TableCell align="left">{formatMoney(l.unit_price)}</TableCell>
                  <TableCell align="left">
                    {Number(l.discount_percent) ? `${Number(l.discount_percent)}%` : ""}
                  </TableCell>
                  <TableCell align="left">{formatMoney(l.line_total)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {doc.payments.length > 0 && (
        <Card variant="outlined">
          <CardContent>
            <Typography variant="h6" component="h2">
              {t("editor.payments")}
            </Typography>
            {doc.payments.map((p) => (
              <Stack key={p.id} direction="row" sx={{ justifyContent: "space-between", py: 0.5 }}>
                <Typography>
                  {t(`payMethods.${p.method}`)} · {formatDate(p.payment_date)}
                </Typography>
                <Typography>{formatMoney(p.amount)}</Typography>
              </Stack>
            ))}
          </CardContent>
        </Card>
      )}

      <Card variant="outlined" sx={{ alignSelf: { md: "flex-end" }, minWidth: { md: 360 } }}>
        <CardContent>
          {showVat && (
            <>
              <Stack direction="row" sx={{ justifyContent: "space-between" }}>
                <Typography>{t("editor.subtotal")}</Typography>
                <Typography>{formatMoney(doc.subtotal)}</Typography>
              </Stack>
              <Stack direction="row" sx={{ justifyContent: "space-between" }}>
                <Typography>
                  {t("editor.vatAmount", { rate: Math.round(Number(doc.vat_rate) * 1000) / 10 })}
                </Typography>
                <Typography>{formatMoney(doc.vat_amount)}</Typography>
              </Stack>
            </>
          )}
          <Stack direction="row" sx={{ justifyContent: "space-between", mt: 1 }}>
            <Typography sx={{ fontWeight: 700 }}>{t("editor.total")}</Typography>
            <Typography sx={{ fontWeight: 700, fontSize: "1.2rem" }}>
              {formatMoney(doc.total)}
            </Typography>
          </Stack>
          {doc.balance_due !== null && doc.type !== "tax_invoice_receipt" && (
            <>
              {Number(doc.amount_paid) > 0 && (
                <Stack direction="row" sx={{ justifyContent: "space-between" }}>
                  <Typography>{t("view.paid")}</Typography>
                  <Typography>{formatMoney(doc.amount_paid)}</Typography>
                </Stack>
              )}
              {Number(doc.amount_credited) > 0 && (
                <Stack direction="row" sx={{ justifyContent: "space-between" }}>
                  <Typography>{t("view.credited")}</Typography>
                  <Typography>{formatMoney(doc.amount_credited)}</Typography>
                </Stack>
              )}
              <Stack direction="row" sx={{ justifyContent: "space-between" }}>
                <Typography sx={{ fontWeight: 500 }}>{t("view.balance")}</Typography>
                <Typography sx={{ fontWeight: 500 }}>{formatMoney(doc.balance_due)}</Typography>
              </Stack>
            </>
          )}
        </CardContent>
      </Card>

      {doc.deliveries.length > 0 && (
        <Card variant="outlined">
          <CardContent>
            <Typography variant="h6" component="h2">
              {t("email.history")}
            </Typography>
            {doc.deliveries.map((d) => (
              <Stack
                key={d.id}
                direction="row"
                spacing={1}
                sx={{ alignItems: "center", py: 0.5, flexWrap: "wrap" }}
              >
                <Chip
                  size="small"
                  label={t(`email.status.${d.status}`)}
                  color={
                    d.status === "sent" ? "success" : d.status === "failed" ? "error" : "default"
                  }
                />
                <Typography dir="ltr">{d.recipients.join(", ")}</Typography>
                <Typography variant="body2" color="text.secondary">
                  {new Date(d.sent_at ?? d.created_at).toLocaleString("he-IL")} ·{" "}
                  {t(`email.variant.${d.variant}`)}
                </Typography>
              </Stack>
            ))}
          </CardContent>
        </Card>
      )}

      <Dialog open={confirmOriginal} onClose={() => setConfirmOriginal(false)} maxWidth="sm">
        <DialogTitle>{t("view.originalDialog.title")}</DialogTitle>
        <DialogContent>
          <DialogContentText>{t("view.originalDialog.body")}</DialogContentText>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2, flexWrap: "wrap", gap: 1 }}>
          <Button onClick={() => setConfirmOriginal(false)}>{t("common.cancel")}</Button>
          {canEdit && (
            <Button
              variant="outlined"
              startIcon={<MailOutlined />}
              onClick={() => {
                setConfirmOriginal(false);
                setEmailing(true);
              }}
            >
              {t("view.originalDialog.email")}
            </Button>
          )}
          <Button variant="contained" onClick={downloadOriginal}>
            {t("view.originalDialog.download")}
          </Button>
        </DialogActions>
      </Dialog>

      {emailing && (
        <SendEmailDialog
          businessId={businessId}
          documentId={doc.id}
          originalSent={Boolean(doc.original_delivered_at)}
          onClose={() => setEmailing(false)}
        />
      )}

      {doc.notes && <Typography sx={{ whiteSpace: "pre-wrap" }}>{doc.notes}</Typography>}

      {doc.related.length > 0 && (
        <Card variant="outlined">
          <CardContent>
            <Typography variant="h6" component="h2">
              {t("view.related")}
            </Typography>
            {doc.related.map((r) => (
              <Typography key={`${r.id}-${r.relation}`}>
                {t(`view.relation_${r.relation}${r.direction === "incoming" ? "_in" : ""}`)}:{" "}
                <Link component={RouterLink} to={`/documents/${r.id}`}>
                  {t(`docTypes.${r.type}`)}{" "}
                  {r.number ? `${t("documents.number")} ${r.number}` : `(${t("docStatus.draft")})`}
                </Link>
                {r.amount && ` · ${formatMoney(r.amount)}`}
              </Typography>
            ))}
          </CardContent>
        </Card>
      )}
    </Stack>
  );
}
