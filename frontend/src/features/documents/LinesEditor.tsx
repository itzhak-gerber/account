import AddIcon from "@mui/icons-material/Add";
import DeleteOutlined from "@mui/icons-material/DeleteOutlined";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Grid from "@mui/material/Grid";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useQuery } from "@tanstack/react-query";
import { useDeferredValue, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { Item, LineInput, VatType } from "../../api/types";
import { formatMoney } from "../../lib/money";
import { EMPTY_LINE } from "./helpers";

function ItemField({
  businessId,
  line,
  onChange,
}: {
  businessId: string;
  line: LineInput;
  onChange: (patch: Partial<LineInput>) => void;
}) {
  const { t } = useTranslation();
  const [input, setInput] = useState(line.description);
  const q = useDeferredValue(input);
  const items = useQuery({
    queryKey: ["business", businessId, "items", q],
    queryFn: () =>
      api.get<Item[]>(`/businesses/${businessId}/items?limit=20&q=${encodeURIComponent(q)}`),
  });
  return (
    <Autocomplete<Item, false, false, true>
      freeSolo
      options={items.data ?? []}
      filterOptions={(x) => x}
      getOptionLabel={(o) => (typeof o === "string" ? o : o.name)}
      inputValue={input}
      onInputChange={(_, value, reason) => {
        setInput(value);
        if (reason === "input") onChange({ description: value, item_id: null });
      }}
      onChange={(_, value) => {
        if (value && typeof value !== "string") {
          setInput(value.name);
          onChange({
            item_id: value.id,
            description: value.name,
            unit_price: value.unit_price,
            unit_of_measure: value.unit_of_measure,
            vat_type: value.vat_type,
          });
        }
      }}
      renderOption={(props, option) => (
        <li {...props} key={option.id}>
          <Box sx={{ display: "flex", justifyContent: "space-between", width: "100%", gap: 2 }}>
            <span>{option.name}</span>
            <span style={{ opacity: 0.7 }}>{formatMoney(option.unit_price)}</span>
          </Box>
        </li>
      )}
      renderInput={(params) => (
        <TextField
          {...params}
          size="small"
          label={t("editor.description")}
          placeholder={t("editor.itemSearch")}
        />
      )}
    />
  );
}

interface Props {
  businessId: string;
  lines: LineInput[];
  lineTotals: number[];
  showVat: boolean;
  pricesIncludeVat: boolean;
  onChange: (lines: LineInput[]) => void;
}

export function LinesEditor({
  businessId,
  lines,
  lineTotals,
  showVat,
  pricesIncludeVat,
  onChange,
}: Props) {
  const { t } = useTranslation();
  const update = (index: number, patch: Partial<LineInput>) =>
    onChange(lines.map((line, i) => (i === index ? { ...line, ...patch } : line)));
  const numeric = (index: number, field: "quantity" | "unit_price" | "discount_percent") => ({
    value: lines[index][field],
    onChange: (e: { target: { value: string } }) =>
      update(index, { [field]: e.target.value.replace(/[^\d.]/g, "") }),
    size: "small" as const,
    fullWidth: true,
    slotProps: { htmlInput: { dir: "ltr", inputMode: "decimal" as const } },
  });

  return (
    <Box>
      {lines.map((line, index) => (
        // Positions are stable while editing; lines are only appended or removed.
        <Paper key={index} variant="outlined" sx={{ p: 1.5, mb: 1.5 }}>
          <Grid container spacing={1.5} sx={{ alignItems: "center" }}>
            <Grid size={{ xs: 12, md: showVat ? 4 : 5 }}>
              <ItemField businessId={businessId} line={line} onChange={(p) => update(index, p)} />
            </Grid>
            <Grid size={{ xs: 4, md: 1.5 }}>
              <TextField label={t("editor.quantity")} {...numeric(index, "quantity")} />
            </Grid>
            <Grid size={{ xs: 4, md: 2 }}>
              <TextField
                label={pricesIncludeVat ? `${t("editor.unitPrice")} (כולל)` : t("editor.unitPrice")}
                {...numeric(index, "unit_price")}
              />
            </Grid>
            <Grid size={{ xs: 4, md: 1.5 }}>
              <TextField label={t("editor.discount")} {...numeric(index, "discount_percent")} />
            </Grid>
            {showVat && (
              <Grid size={{ xs: 6, md: 1.5 }}>
                <TextField
                  select
                  size="small"
                  fullWidth
                  label={t("editor.vat")}
                  value={line.vat_type}
                  onChange={(e) => update(index, { vat_type: e.target.value as VatType })}
                >
                  {(["standard", "exempt", "zero"] as const).map((v) => (
                    <MenuItem key={v} value={v}>
                      {t(`vatTypes.${v}`)}
                    </MenuItem>
                  ))}
                </TextField>
              </Grid>
            )}
            <Grid size={{ xs: showVat ? 4 : 10, md: 1 }}>
              <Typography sx={{ fontWeight: 500, textAlign: { xs: "start", md: "end" } }}>
                {formatMoney(lineTotals[index] ?? 0)}
              </Typography>
            </Grid>
            <Grid size={{ xs: 2, md: 0.5 }} sx={{ textAlign: "end" }}>
              <IconButton
                aria-label={t("editor.removeLine")}
                onClick={() => onChange(lines.filter((_, i) => i !== index))}
                size="small"
              >
                <DeleteOutlined />
              </IconButton>
            </Grid>
          </Grid>
        </Paper>
      ))}
      <Button startIcon={<AddIcon />} onClick={() => onChange([...lines, { ...EMPTY_LINE }])}>
        {t("editor.addLine")}
      </Button>
    </Box>
  );
}
