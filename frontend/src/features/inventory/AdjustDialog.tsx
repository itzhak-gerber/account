import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { StockItem, StockMovement } from "../../api/types";
import { cleanAmount, finishAmount } from "../../lib/amount";
import { errorMessage } from "../../lib/errors";

type Mode = "count" | "add" | "remove";

/** A stock count (the quantity on the shelf) or a correction, always with a reason. */
export function AdjustDialog({
  businessId,
  row,
  onClose,
}: {
  businessId: string;
  row: StockItem;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<Mode>("count");
  const [quantity, setQuantity] = useState("");
  const [cost, setCost] = useState("");
  const [reason, setReason] = useState("");
  const [touched, setTouched] = useState(false);
  const save = useMutation({
    mutationFn: () => {
      const q = finishAmount(quantity);
      return api.post<StockMovement>(
        `/businesses/${businessId}/inventory/${row.item.id}/adjustments`,
        {
          reason: reason.trim(),
          ...(mode === "count" ? { counted: q } : { change: mode === "add" ? q : `-${q}` }),
          ...(mode === "add" && cost ? { unit_cost: finishAmount(cost) } : {}),
        },
      );
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["business", businessId, "inventory"] });
      onClose();
    },
  });
  const ok = quantity !== "" && reason.trim() !== "";
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (ok) save.mutate();
  };

  return (
    <Dialog open onClose={onClose} maxWidth="xs" fullWidth>
      <form onSubmit={submit} noValidate>
        <DialogTitle>{t("inventory.adjustTitle", { name: row.item.name })}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <Typography color="text.secondary">
              {t("inventory.onHand", { quantity: Number(row.quantity) })}
            </Typography>
            {save.isError && <Alert severity="error">{errorMessage(t, save.error)}</Alert>}
            <ToggleButtonGroup
              exclusive
              fullWidth
              size="small"
              value={mode}
              onChange={(_, value: Mode | null) => value && setMode(value)}
              aria-label={t("inventory.adjustKind")}
            >
              <ToggleButton value="count">{t("inventory.modes.count")}</ToggleButton>
              <ToggleButton value="add">{t("inventory.modes.add")}</ToggleButton>
              <ToggleButton value="remove">{t("inventory.modes.remove")}</ToggleButton>
            </ToggleButtonGroup>
            <TextField
              autoFocus
              required
              label={t(`inventory.quantityLabel.${mode}`)}
              value={quantity}
              error={touched && quantity === ""}
              onChange={(e) => setQuantity(cleanAmount(e.target.value, 3))}
              slotProps={{ htmlInput: { dir: "ltr", inputMode: "decimal" } }}
            />
            {mode === "add" && (
              <TextField
                label={t("inventory.unitCost")}
                helperText={t("inventory.unitCostHelp")}
                value={cost}
                onChange={(e) => setCost(cleanAmount(e.target.value, 4))}
                slotProps={{ htmlInput: { dir: "ltr", inputMode: "decimal" } }}
              />
            )}
            <TextField
              required
              label={t("inventory.reason")}
              placeholder={t("inventory.reasonExample")}
              value={reason}
              error={touched && reason.trim() === ""}
              onChange={(e) => setReason(e.target.value)}
            />
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={onClose}>{t("common.cancel")}</Button>
          <Button type="submit" variant="contained" disabled={save.isPending}>
            {t("inventory.save")}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
