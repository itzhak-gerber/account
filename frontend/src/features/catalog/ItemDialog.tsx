import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControlLabel from "@mui/material/FormControlLabel";
import Grid from "@mui/material/Grid";
import MenuItem from "@mui/material/MenuItem";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { Item, ItemInput } from "../../api/types";
import { cleanAmount, finishAmount, isAmount } from "../../lib/amount";
import { errorMessage } from "../../lib/errors";
import { KitComponentsEditor } from "./KitComponentsEditor";

const EMPTY: ItemInput = {
  name: "",
  description: "",
  item_type: "service",
  sku: "",
  barcode: "",
  unit_of_measure: "",
  unit_price: "",
  vat_type: "standard",
  track_inventory: false,
  min_stock: null,
  components: [],
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
  const [value, setValue] = useState<ItemInput>(
    item ? { ...item, components: item.components.map((c) => ({ ...c })) } : EMPTY,
  );
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

  const priceOk = isAmount(value.unit_price);
  const isKit = value.item_type === "kit";
  const componentsOk =
    !isKit ||
    (value.components.length > 0 &&
      value.components.every((c) => c.item_id && Number(c.quantity) > 0));
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (!value.name.trim() || !priceOk || !componentsOk) return;
    save.mutate({
      ...value,
      unit_price: finishAmount(value.unit_price),
      min_stock:
        value.item_type === "product" && value.track_inventory && value.min_stock
          ? finishAmount(value.min_stock)
          : null,
      components: isKit
        ? value.components.map((c) => ({ ...c, quantity: finishAmount(c.quantity) }))
        : [],
    });
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
                helperText: touched && !priceOk ? t("amount.invalid") : t("amount.example"),
                onChange: (e: { target: { value: string } }) =>
                  setValue((v) => ({ ...v, unit_price: cleanAmount(e.target.value) })),
                slotProps: { htmlInput: { dir: "ltr", inputMode: "decimal" } },
              })}
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>{field("unit_of_measure")}</Grid>
            <Grid size={{ xs: 6 }}>
              {field("item_type", {
                select: true,
                children: (["service", "product", "kit"] as const).map((v) => (
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
            {value.item_type === "product" && (
              <>
                <Grid size={{ xs: 12, sm: 6 }} sx={{ display: "flex", alignItems: "center" }}>
                  <FormControlLabel
                    control={
                      <Switch
                        checked={value.track_inventory}
                        onChange={(e) =>
                          setValue((v) => ({ ...v, track_inventory: e.target.checked }))
                        }
                      />
                    }
                    label={t("items.track_inventory")}
                  />
                </Grid>
                {value.track_inventory && (
                  <Grid size={{ xs: 12, sm: 6 }}>
                    <TextField
                      label={t("items.min_stock")}
                      helperText={t("items.minStockHelp")}
                      value={value.min_stock ?? ""}
                      onChange={(e) =>
                        setValue((v) => ({
                          ...v,
                          min_stock: cleanAmount(e.target.value, 3) || null,
                        }))
                      }
                      fullWidth
                      slotProps={{ htmlInput: { dir: "ltr", inputMode: "decimal" } }}
                    />
                  </Grid>
                )}
              </>
            )}
            {isKit && (
              <Grid size={12}>
                <KitComponentsEditor
                  businessId={businessId}
                  kitId={item?.id ?? null}
                  components={value.components}
                  error={touched && !componentsOk}
                  onChange={(components) => setValue((v) => ({ ...v, components }))}
                />
              </Grid>
            )}
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
