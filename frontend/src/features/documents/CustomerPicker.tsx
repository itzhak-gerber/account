import Autocomplete from "@mui/material/Autocomplete";
import Button from "@mui/material/Button";
import Collapse from "@mui/material/Collapse";
import Grid from "@mui/material/Grid";
import TextField from "@mui/material/TextField";
import { useQuery } from "@tanstack/react-query";
import { useDeferredValue, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { Customer, CustomerDetails } from "../../api/types";
import { CustomerDialog } from "../catalog/CustomerDialog";
import { detailsFromCustomer } from "./helpers";

interface Props {
  businessId: string;
  customerId: string | null;
  details: CustomerDetails;
  canSaveCustomer: boolean;
  onChange: (customerId: string | null, details: CustomerDetails) => void;
}

export function CustomerPicker({
  businessId,
  customerId,
  details,
  canSaveCustomer,
  onChange,
}: Props) {
  const { t } = useTranslation();
  const [input, setInput] = useState(details.name);
  const q = useDeferredValue(input);
  const [showDetails, setShowDetails] = useState(false);
  const [creating, setCreating] = useState(false);
  const customers = useQuery({
    queryKey: ["business", businessId, "customers", q],
    queryFn: () =>
      api.get<Customer[]>(
        `/businesses/${businessId}/customers?limit=20&q=${encodeURIComponent(q)}`,
      ),
  });

  const set = (field: keyof CustomerDetails) => (e: { target: { value: string } }) =>
    onChange(customerId, { ...details, [field]: e.target.value });

  return (
    <>
      <Autocomplete<Customer, false, false, true>
        freeSolo
        options={customers.data ?? []}
        getOptionLabel={(option) => (typeof option === "string" ? option : option.name)}
        filterOptions={(x) => x}
        inputValue={input}
        onInputChange={(_, value, reason) => {
          setInput(value);
          if (reason === "input") onChange(null, { ...details, name: value });
        }}
        onChange={(_, value) => {
          if (value && typeof value !== "string") {
            setInput(value.name);
            onChange(value.id, detailsFromCustomer(value));
          }
        }}
        renderOption={(props, option) => (
          <li {...props} key={option.id}>
            {option.name}
            {option.tax_id && (
              <span style={{ marginInlineStart: 8, opacity: 0.6 }}>{option.tax_id}</span>
            )}
          </li>
        )}
        renderInput={(params) => (
          <TextField
            {...params}
            label={t("editor.customer")}
            placeholder={t("editor.customerSearch")}
          />
        )}
      />
      <Grid container spacing={1} sx={{ mt: 0.5 }}>
        <Grid>
          <Button size="small" onClick={() => setShowDetails((v) => !v)}>
            {t("editor.customerDetails")}
          </Button>
        </Grid>
        {canSaveCustomer && !customerId && details.name.trim() && (
          <Grid>
            <Button size="small" onClick={() => setCreating(true)}>
              {t("editor.saveCustomer")}
            </Button>
          </Grid>
        )}
      </Grid>
      <Collapse in={showDetails}>
        <Grid container spacing={2} sx={{ pt: 1 }}>
          {(
            ["tax_id", "phone", "email", "address_street", "address_city", "address_zip"] as const
          ).map((field) => (
            <Grid
              key={field}
              size={{ xs: 12, sm: field === "address_zip" ? 3 : field === "address_city" ? 5 : 6 }}
            >
              <TextField
                label={t(`customers.${field}`)}
                value={details[field] ?? ""}
                onChange={set(field)}
                fullWidth
                size="small"
                slotProps={{
                  htmlInput: ["tax_id", "phone", "email"].includes(field) ? { dir: "ltr" } : {},
                }}
              />
            </Grid>
          ))}
        </Grid>
      </Collapse>
      {creating && (
        <CustomerDialog
          open
          businessId={businessId}
          customer={null}
          initialName={details.name}
          onClose={() => setCreating(false)}
          onSaved={(c) => {
            setInput(c.name);
            onChange(c.id, detailsFromCustomer(c));
          }}
        />
      )}
    </>
  );
}
