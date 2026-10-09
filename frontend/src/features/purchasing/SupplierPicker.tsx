import Autocomplete from "@mui/material/Autocomplete";
import TextField from "@mui/material/TextField";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { Supplier } from "../../api/types";

interface Props {
  businessId: string;
  value: string;
  onChange: (supplierId: string) => void;
  error?: boolean;
  disabled?: boolean;
}

export function SupplierPicker({ businessId, value, onChange, error, disabled }: Props) {
  const { t } = useTranslation();
  const suppliers = useQuery({
    queryKey: ["business", businessId, "suppliers", "active"],
    queryFn: () => api.get<Supplier[]>(`/businesses/${businessId}/suppliers?limit=200&q=`),
  });
  const options = suppliers.data ?? [];
  return (
    <Autocomplete
      options={options}
      disabled={disabled}
      getOptionLabel={(s) => s.name}
      value={options.find((s) => s.id === value) ?? null}
      onChange={(_, picked) => onChange(picked?.id ?? "")}
      noOptionsText={t("suppliers.noneYet")}
      renderInput={(params) => (
        <TextField
          {...params}
          label={t("purchasing.supplier")}
          required
          error={error}
          helperText={error ? t("common.required") : undefined}
        />
      )}
    />
  );
}
