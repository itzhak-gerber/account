import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Grid from "@mui/material/Grid";
import TextField from "@mui/material/TextField";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { Customer, CustomerInput } from "../../api/types";
import { errorMessage } from "../../lib/errors";
import { isValidIsraeliTaxId } from "../../lib/taxId";

const EMPTY: CustomerInput = {
  name: "",
  tax_id: "",
  email: "",
  phone: "",
  address_street: "",
  address_city: "",
  address_zip: "",
  notes: "",
};

interface Props {
  businessId: string;
  customer: Customer | null; // null = new
  initialName?: string;
  open: boolean;
  onClose: () => void;
  onSaved?: (customer: Customer) => void;
}

export function CustomerDialog({
  businessId,
  customer,
  initialName,
  open,
  onClose,
  onSaved,
}: Props) {
  const { t } = useTranslation();
  const fullScreen = useMediaQuery(useTheme().breakpoints.down("sm"));
  const queryClient = useQueryClient();
  const [value, setValue] = useState<CustomerInput>(
    customer ? { ...customer } : { ...EMPTY, name: initialName ?? "" },
  );
  const [touched, setTouched] = useState(false);
  const base = `/businesses/${businessId}/customers`;

  const save = useMutation({
    mutationFn: (input: CustomerInput) =>
      customer
        ? api.patch<Customer>(`${base}/${customer.id}`, input)
        : api.post<Customer>(base, input),
    onSuccess: async (saved) => {
      await queryClient.invalidateQueries({ queryKey: ["business", businessId, "customers"] });
      onSaved?.(saved);
      onClose();
    },
  });

  const taxIdError = touched && value.tax_id !== "" && !isValidIsraeliTaxId(value.tax_id);
  const nameError = touched && !value.name.trim();
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (!value.name.trim() || (value.tax_id && !isValidIsraeliTaxId(value.tax_id))) return;
    save.mutate({ ...value, email: value.email?.trim() || null });
  };
  const field = (name: keyof CustomerInput, props: Record<string, unknown> = {}) => (
    <TextField
      label={t(`customers.${name}`)}
      value={value[name] ?? ""}
      onChange={(e) => setValue((v) => ({ ...v, [name]: e.target.value }))}
      fullWidth
      {...props}
    />
  );

  return (
    <Dialog open={open} onClose={onClose} fullScreen={fullScreen} maxWidth="sm" fullWidth>
      <form onSubmit={submit} noValidate>
        <DialogTitle>{customer ? t("customers.edit") : t("customers.new")}</DialogTitle>
        <DialogContent>
          {save.isError && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {errorMessage(t, save.error)}
            </Alert>
          )}
          <Grid container spacing={2} sx={{ pt: 1 }}>
            <Grid size={12}>
              {field("name", {
                required: true,
                autoFocus: true,
                error: nameError,
                helperText: nameError ? t("common.required") : undefined,
              })}
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              {field("tax_id", {
                error: taxIdError,
                helperText: taxIdError ? t("business.invalidTaxId") : undefined,
                slotProps: { htmlInput: { dir: "ltr", inputMode: "numeric" } },
              })}
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              {field("phone", { slotProps: { htmlInput: { dir: "ltr", inputMode: "tel" } } })}
            </Grid>
            <Grid size={12}>
              {field("email", { type: "email", slotProps: { htmlInput: { dir: "ltr" } } })}
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>{field("address_street")}</Grid>
            <Grid size={{ xs: 8, sm: 4 }}>{field("address_city")}</Grid>
            <Grid size={{ xs: 4, sm: 2 }}>{field("address_zip")}</Grid>
            <Grid size={12}>{field("notes", { multiline: true, minRows: 2 })}</Grid>
          </Grid>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={onClose}>{t("common.cancel")}</Button>
          <Button type="submit" variant="contained" disabled={save.isPending}>
            {t("customers.save")}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
