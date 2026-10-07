import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import { useTranslation } from "react-i18next";

import { PRESETS, presetPeriod, type Period, type PresetKey } from "./periods";
import { israelToday } from "../documents/helpers";

export function PeriodPicker({
  preset,
  period,
  onChange,
}: {
  preset: PresetKey;
  period: Period;
  onChange: (preset: PresetKey, period: Period) => void;
}) {
  const { t } = useTranslation();
  return (
    <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
      <TextField
        select
        label={t("reports.period")}
        value={preset}
        onChange={(e) => {
          const next = e.target.value as PresetKey;
          onChange(next, next === "custom" ? period : presetPeriod(next, israelToday()));
        }}
        sx={{ minWidth: 240 }}
      >
        {PRESETS.map((p) => (
          <MenuItem key={p} value={p}>
            {t(`reports.presets.${p}`)}
          </MenuItem>
        ))}
      </TextField>
      <TextField
        type="date"
        label={t("reports.from")}
        value={period.from}
        onChange={(e) => e.target.value && onChange("custom", { ...period, from: e.target.value })}
        slotProps={{ inputLabel: { shrink: true } }}
      />
      <TextField
        type="date"
        label={t("reports.to")}
        value={period.to}
        onChange={(e) => e.target.value && onChange("custom", { ...period, to: e.target.value })}
        slotProps={{ inputLabel: { shrink: true } }}
      />
    </Stack>
  );
}
