import DeleteOutlined from "@mui/icons-material/DeleteOutlined";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Grid from "@mui/material/Grid";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { DocumentSummary } from "../../api/types";
import { formatDate, formatMoney } from "../../lib/money";
import type { AllocationRow } from "./helpers";

interface Props {
  businessId: string;
  customerId: string | null;
  rows: AllocationRow[];
  paymentsTotal: number;
  onChange: (rows: AllocationRow[]) => void;
  onFillPayment: (amount: number) => void;
}

export function AllocationsEditor({
  businessId,
  customerId,
  rows,
  paymentsTotal,
  onChange,
  onFillPayment,
}: Props) {
  const { t } = useTranslation();
  const [input, setInput] = useState("");
  const params = new URLSearchParams({ open_only: "true", limit: "100" });
  if (customerId) params.set("customer_id", customerId);
  const open = useQuery({
    queryKey: ["business", businessId, "documents", "open", params.toString()],
    queryFn: () => api.get<DocumentSummary[]>(`/businesses/${businessId}/documents?${params}`),
  });
  const chosen = new Set(rows.map((r) => r.invoice_id));
  const options = (open.data ?? []).filter((d) => !chosen.has(d.id));
  const label = (d: DocumentSummary) =>
    `${t(`docTypes.${d.type}`)} ${t("documents.number")} ${d.number} · ${d.customer_name} · ${formatDate(d.issue_date)}`;
  const allocated = rows.reduce((s, r) => s + Number(r.amount || 0), 0);

  return (
    <Box>
      <Typography variant="h6" component="h2">
        {t("allocations.title")}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
        {t("allocations.help")}
      </Typography>
      {rows.map((row, index) => (
        <Paper key={row.invoice_id} variant="outlined" sx={{ p: 1.5, mb: 1.5 }}>
          <Grid container spacing={1.5} sx={{ alignItems: "center" }}>
            <Grid size={{ xs: 12, md: 7 }}>
              <Typography>{row.label}</Typography>
              <Typography variant="body2" color="text.secondary">
                {t("allocations.balance")}: {formatMoney(row.balance)}
              </Typography>
            </Grid>
            <Grid size={{ xs: 10, md: 4 }}>
              <TextField
                size="small"
                fullWidth
                label={t("allocations.amount")}
                value={row.amount}
                error={Number(row.amount) > Number(row.balance) || !(Number(row.amount) > 0)}
                onChange={(e) =>
                  onChange(
                    rows.map((r, i) =>
                      i === index ? { ...r, amount: e.target.value.replace(/[^\d.]/g, "") } : r,
                    ),
                  )
                }
                slotProps={{ htmlInput: { dir: "ltr", inputMode: "decimal" } }}
              />
            </Grid>
            <Grid size={{ xs: 2, md: 1 }} sx={{ textAlign: "end" }}>
              <IconButton
                aria-label={t("editor.removeLine")}
                size="small"
                onClick={() => onChange(rows.filter((_, i) => i !== index))}
              >
                <DeleteOutlined />
              </IconButton>
            </Grid>
          </Grid>
        </Paper>
      ))}
      <Autocomplete<DocumentSummary>
        options={options}
        getOptionLabel={label}
        value={null}
        inputValue={input}
        onInputChange={(_, value) => setInput(value)}
        noOptionsText={t("allocations.none")}
        onChange={(_, invoice) => {
          if (!invoice) return;
          setInput("");
          onChange([
            ...rows,
            {
              invoice_id: invoice.id,
              amount: invoice.balance_due ?? invoice.total,
              balance: invoice.balance_due ?? invoice.total,
              label: label(invoice),
            },
          ]);
        }}
        renderOption={(props, option) => (
          <li {...props} key={option.id}>
            <Box sx={{ display: "flex", justifyContent: "space-between", width: "100%", gap: 2 }}>
              <span>{label(option)}</span>
              <span style={{ opacity: 0.7 }}>
                {formatMoney(option.balance_due ?? option.total)}
              </span>
            </Box>
          </li>
        )}
        renderInput={(params) => (
          <TextField {...params} size="small" label={t("allocations.pick")} />
        )}
      />
      {rows.length > 0 && (
        <Box sx={{ mt: 1.5, display: "flex", gap: 2, alignItems: "center", flexWrap: "wrap" }}>
          <Typography sx={{ fontWeight: 500 }}>
            {t("allocations.total")}: {formatMoney(allocated)}
          </Typography>
          {Math.abs(allocated - paymentsTotal) > 0.004 && (
            <Button size="small" onClick={() => onFillPayment(allocated)}>
              {t("allocations.fillPayment")}
            </Button>
          )}
          {paymentsTotal - allocated > 0.004 && (
            <Typography variant="body2" color="text.secondary">
              {t("allocations.unallocated", { amount: formatMoney(paymentsTotal - allocated) })}
            </Typography>
          )}
        </Box>
      )}
    </Box>
  );
}
