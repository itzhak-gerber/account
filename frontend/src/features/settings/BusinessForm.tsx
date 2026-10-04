import Button from "@mui/material/Button";
import Grid from "@mui/material/Grid";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import type { BusinessInput, BusinessType } from "../../api/types";
import { isValidIsraeliTaxId } from "../../lib/taxId";

const TYPES: BusinessType[] = ["licensed_dealer", "exempt_dealer", "company", "nonprofit"];

interface Props {
  initial: BusinessInput;
  submitLabel: string;
  disabled?: boolean;
  busy?: boolean;
  onSubmit: (value: BusinessInput) => void;
}

export function BusinessForm({ initial, submitLabel, disabled, busy, onSubmit }: Props) {
  const { t } = useTranslation();
  const [value, setValue] = useState<BusinessInput>(initial);
  const [touched, setTouched] = useState(false);

  const set = (field: keyof BusinessInput) => (e: { target: { value: string } }) =>
    setValue((v) => ({ ...v, [field]: e.target.value }));

  const taxIdError = touched && !isValidIsraeliTaxId(value.tax_id);
  const nameError = touched && !value.legal_name.trim();

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (!value.legal_name.trim() || !isValidIsraeliTaxId(value.tax_id)) return;
    onSubmit({
      ...value,
      display_name: value.display_name.trim() || value.legal_name,
      email: value.email?.trim() || null,
    });
  };

  const field = (name: keyof BusinessInput, props: Record<string, unknown> = {}) => (
    <TextField
      label={t(`business.${name}`)}
      value={value[name] ?? ""}
      onChange={set(name)}
      fullWidth
      disabled={disabled}
      {...props}
    />
  );

  return (
    <form onSubmit={submit} noValidate>
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 6 }}>
          {field("legal_name", {
            required: true,
            error: nameError,
            helperText: nameError ? t("common.required") : " ",
          })}
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>{field("display_name", { helperText: " " })}</Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          {field("tax_id", {
            required: true,
            error: taxIdError,
            helperText: taxIdError ? t("business.invalidTaxId") : " ",
            slotProps: { htmlInput: { inputMode: "numeric", dir: "ltr" } },
          })}
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          {field("business_type", {
            select: true,
            helperText: " ",
            children: TYPES.map((type) => (
              <MenuItem key={type} value={type}>
                {t(`business.types.${type}`)}
              </MenuItem>
            )),
          })}
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>{field("address_street")}</Grid>
        <Grid size={{ xs: 8, md: 4 }}>{field("address_city")}</Grid>
        <Grid size={{ xs: 4, md: 2 }}>
          {field("address_zip", { slotProps: { htmlInput: { dir: "ltr" } } })}
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          {field("phone", { slotProps: { htmlInput: { dir: "ltr", inputMode: "tel" } } })}
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          {field("email", { type: "email", slotProps: { htmlInput: { dir: "ltr" } } })}
        </Grid>
        {!disabled && (
          <Grid size={12}>
            <Button type="submit" variant="contained" size="large" disabled={busy}>
              {submitLabel}
            </Button>
          </Grid>
        )}
      </Grid>
    </form>
  );
}
