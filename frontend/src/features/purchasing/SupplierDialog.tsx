import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControlLabel from "@mui/material/FormControlLabel";
import Grid from "@mui/material/Grid";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { Supplier, SupplierInput } from "../../api/types";
import { errorMessage } from "../../lib/errors";
import { isValidIsraeliTaxId } from "../../lib/taxId";

const EMPTY: SupplierInput = {
  name: "",
  tax_id: "",
  contact_name: "",
  email: "",
  phone: "",
  address_street: "",
  address_city: "",
  address_zip: "",
  notes: "",
};

interface Props {
  businessId: string;
  supplier: Supplier | null; // null = new
  onClose: () => void;
}

export function SupplierDialog({ businessId, supplier, onClose }: Props) {
  const { t } = useTranslation();
  const fullScreen = useMediaQuery(useTheme().breakpoints.down("sm"));
  const queryClient = useQueryClient();
  const [value, setValue] = useState<SupplierInput>(supplier ? { ...supplier } : EMPTY);
  const [archived, setArchived] = useState(supplier?.is_archived ?? false);
  const [touched, setTouched] = useState(false);
  const base = `/businesses/${businessId}/suppliers`;

  const save = useMutation({
    mutationFn: (input: SupplierInput) =>
      supplier
        ? api.patch<Supplier>(`${base}/${supplier.id}`, { ...input, is_archived: archived })
        : api.post<Supplier>(base, input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["business", businessId, "suppliers"] });
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
  const field = (name: keyof SupplierInput, props: Record<string, unknown> = {}) => (
    <TextField
      label={t(`suppliers.${name}`)}
      value={value[name] ?? ""}
      onChange={(e) => setValue((v) => ({ ...v, [name]: e.target.value }))}
      fullWidth
      {...props}
    />
  );

  return (
    <Dialog open onClose={onClose} fullScreen={fullScreen} maxWidth="sm" fullWidth>
      <form onSubmit={submit} noValidate>
        <DialogTitle>{supplier ? t("suppliers.edit") : t("suppliers.new")}</DialogTitle>
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
            <Grid size={{ xs: 12, sm: 6 }}>{field("contact_name")}</Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              {field("phone", { slotProps: { htmlInput: { dir: "ltr", inputMode: "tel" } } })}
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              {field("email", { type: "email", slotProps: { htmlInput: { dir: "ltr" } } })}
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>{field("address_street")}</Grid>
            <Grid size={{ xs: 8, sm: 4 }}>{field("address_city")}</Grid>
            <Grid size={{ xs: 4, sm: 2 }}>{field("address_zip")}</Grid>
            <Grid size={12}>{field("notes", { multiline: true, minRows: 2 })}</Grid>
            {supplier && (
              <Grid size={12}>
                <FormControlLabel
                  control={
                    <Switch checked={archived} onChange={(e) => setArchived(e.target.checked)} />
                  }
                  label={t("suppliers.archive")}
                />
              </Grid>
            )}
          </Grid>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={onClose}>{t("common.cancel")}</Button>
          <Button type="submit" variant="contained" disabled={save.isPending}>
            {t("purchasing.save")}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
