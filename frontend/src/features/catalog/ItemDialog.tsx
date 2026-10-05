import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Grid from "@mui/material/Grid";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { Item, ItemInput } from "../../api/types";
import { errorMessage } from "../../lib/errors";

const EMPTY: ItemInput = {
  name: "",
  description: "",
  item_type: "service",
  sku: "",
  barcode: "",
  unit_of_measure: "",
  unit_price: "",
  vat_type: "standard",
};

interface Props {
  businessId: string;
  item: Item | null;
  open: boolean;
  onClose: () => void;
}

export function ItemDialog({ businessId, item, open, onClose }: Props) {
  const { t } = useTranslation();
  const fullScreen = useMediaQuery(useTheme().breakpoints.down("sm"));
  const queryClient = useQueryClient();
  const [value, setValue] = useState<ItemInput>(item ? { ...item } : EMPTY);
  const [touched, setTouched] = useState(false);
  const base = `/businesses/${businessId}/items`;

  const save = useMutation({
    mutationFn: (input: ItemInput) =>
      item ? api.patch<Item>(`${base}/${item.id}`, input) : api.post<Item>(base, input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["business", businessId, "items"] });
      onClose();
    },
  });

  const priceOk = /^\d+(\.\d{1,2})?$/.test(value.unit_price);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (!value.name.trim() || !priceOk) return;
    save.mutate(value);
  };
  const field = (name: keyof ItemInput, props: Record<string, unknown> = {}) => (
    <TextField
      label={t(`items.${name}`)}
      value={value[name] ?? ""}
      onChange={(e) => setValue((v) => ({ ...v, [name]: e.target.value }))}
      fullWidth
      {...props}
    />
  );

  return (
    <Dialog open={open} onClose={onClose} fullScreen={fullScreen} maxWidth="sm" fullWidth>
      <form onSubmit={submit} noValidate>
        <DialogTitle>{item ? t("items.edit") : t("items.new")}</DialogTitle>
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
                error: touched && !value.name.trim(),
              })}
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              {field("unit_price", {
                required: true,
                error: touched && !priceOk,
                slotProps: { htmlInput: { dir: "ltr", inputMode: "decimal" } },
              })}
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>{field("unit_of_measure")}</Grid>
            <Grid size={{ xs: 6 }}>
              {field("item_type", {
                select: true,
                children: (["service", "product"] as const).map((v) => (
                  <MenuItem key={v} value={v}>
                    {t(`items.types.${v}`)}
                  </MenuItem>
                )),
              })}
            </Grid>
            <Grid size={{ xs: 6 }}>
              {field("vat_type", {
                select: true,
                children: (["standard", "exempt", "zero"] as const).map((v) => (
                  <MenuItem key={v} value={v}>
                    {t(`vatTypes.${v}`)}
                  </MenuItem>
                )),
              })}
            </Grid>
            <Grid size={{ xs: 6 }}>
              {field("sku", { slotProps: { htmlInput: { dir: "ltr" } } })}
            </Grid>
            <Grid size={{ xs: 6 }}>
              {field("barcode", { slotProps: { htmlInput: { dir: "ltr" } } })}
            </Grid>
            <Grid size={12}>{field("description", { multiline: true, minRows: 2 })}</Grid>
          </Grid>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={onClose}>{t("common.cancel")}</Button>
          <Button type="submit" variant="contained" disabled={save.isPending}>
            {t("items.save")}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
