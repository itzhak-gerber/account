import AddIcon from "@mui/icons-material/Add";
import DeleteOutlined from "@mui/icons-material/DeleteOutlined";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Grid from "@mui/material/Grid";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import TextField from "@mui/material/TextField";
import { useTranslation } from "react-i18next";

import type { PaymentDetails, PaymentInput, PaymentMethod } from "../../api/types";

const METHODS: PaymentMethod[] = [
  "bank_transfer",
  "credit_card",
  "cash",
  "check",
  "digital_wallet",
  "other",
];

const DETAIL_FIELDS: Record<PaymentMethod, (keyof PaymentDetails)[]> = {
  cash: [],
  check: ["bank", "branch", "account", "check_number"],
  credit_card: ["card_last4", "installments"],
  bank_transfer: ["bank", "reference"],
  digital_wallet: ["reference"],
  other: ["reference"],
};

const LABEL: Record<keyof PaymentDetails, string> = {
  bank: "editor.bank",
  branch: "editor.branch",
  account: "editor.account",
  check_number: "editor.checkNumber",
  card_last4: "editor.cardLast4",
  installments: "editor.installments",
  reference: "editor.reference",
};

interface Props {
  payments: PaymentInput[];
  defaultDate: string;
  remaining: number;
  onChange: (payments: PaymentInput[]) => void;
}

export function PaymentsEditor({ payments, defaultDate, remaining, onChange }: Props) {
  const { t } = useTranslation();
  const update = (index: number, patch: Partial<PaymentInput>) =>
    onChange(payments.map((p, i) => (i === index ? { ...p, ...patch } : p)));

  return (
    <Box>
      {payments.map((p, index) => (
        <Paper key={index} variant="outlined" sx={{ p: 1.5, mb: 1.5 }}>
          <Grid container spacing={1.5} sx={{ alignItems: "center" }}>
            <Grid size={{ xs: 12, sm: 4 }}>
              <TextField
                select
                size="small"
                fullWidth
                label={t("editor.method")}
                value={p.method}
                onChange={(e) =>
                  update(index, { method: e.target.value as PaymentMethod, details: {} })
                }
              >
                {METHODS.map((m) => (
                  <MenuItem key={m} value={m}>
                    {t(`payMethods.${m}`)}
                  </MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid size={{ xs: 6, sm: 3 }}>
              <TextField
                size="small"
                fullWidth
                label={t("editor.amount")}
                value={p.amount}
                onChange={(e) => update(index, { amount: e.target.value.replace(/[^\d.]/g, "") })}
                slotProps={{ htmlInput: { dir: "ltr", inputMode: "decimal" } }}
              />
            </Grid>
            <Grid size={{ xs: 6, sm: 4 }}>
              <TextField
                size="small"
                fullWidth
                type="date"
                label={t("editor.paymentDate")}
                value={p.payment_date}
                onChange={(e) => update(index, { payment_date: e.target.value })}
                slotProps={{ inputLabel: { shrink: true } }}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 1 }} sx={{ textAlign: "end" }}>
              <IconButton
                aria-label={t("editor.removeLine")}
                size="small"
                onClick={() => onChange(payments.filter((_, i) => i !== index))}
              >
                <DeleteOutlined />
              </IconButton>
            </Grid>
            {DETAIL_FIELDS[p.method].map((field) => (
              <Grid key={field} size={{ xs: 6, sm: 3 }}>
                <TextField
                  size="small"
                  fullWidth
                  label={t(LABEL[field])}
                  value={p.details[field] ?? ""}
                  onChange={(e) =>
                    update(index, {
                      details: {
                        ...p.details,
                        [field]:
                          field === "installments"
                            ? e.target.value === ""
                              ? null
                              : Number(e.target.value.replace(/\D/g, ""))
                            : e.target.value,
                      },
                    })
                  }
                  slotProps={{ htmlInput: { dir: "ltr" } }}
                />
              </Grid>
            ))}
          </Grid>
        </Paper>
      ))}
      <Button
        startIcon={<AddIcon />}
        onClick={() =>
          onChange([
            ...payments,
            {
              method: "bank_transfer",
              amount: remaining > 0 ? remaining.toFixed(2) : "",
              payment_date: defaultDate,
              details: {},
            },
          ])
        }
      >
        {t("editor.addPayment")}
      </Button>
    </Box>
  );
}
