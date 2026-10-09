import AddIcon from "@mui/icons-material/Add";
import DeleteOutlined from "@mui/icons-material/DeleteOutlined";
import Autocomplete from "@mui/material/Autocomplete";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { Item } from "../../api/types";
import { cleanAmount } from "../../lib/amount";
import { formatMoney } from "../../lib/money";
import { lineOk, linesTotal, type PurchaseLine } from "./purchaseLines";

interface Props {
  businessId: string;
  lines: PurchaseLine[];
  onChange: (lines: PurchaseLine[]) => void;
  /** Receipts take products only, and every line needs one; orders may have free text. */
  productsOnly: boolean;
  error: boolean;
}

/** Lines of a purchase order or a goods receipt: item, quantity and cost per unit before VAT. */
export function PurchaseLinesEditor({ businessId, lines, onChange, productsOnly, error }: Props) {
  const { t } = useTranslation();
  const items = useQuery({
    queryKey: ["business", businessId, "items", ""],
    queryFn: () => api.get<Item[]>(`/businesses/${businessId}/items?limit=200&q=`),
  });
  const options = (items.data ?? []).filter((i) =>
    productsOnly ? i.item_type === "product" : i.item_type !== "kit",
  );
  const byId = new Map(options.map((i) => [i.id, i]));
  const update = (index: number, patch: Partial<PurchaseLine>) =>
    onChange(lines.map((l, i) => (i === index ? { ...l, ...patch } : l)));

  return (
    <Stack spacing={2} component="fieldset" sx={{ border: 0, p: 0, m: 0 }}>
      <Typography component="legend" variant="h6" sx={{ mb: 1 }}>
        {t("purchasing.lines")}
      </Typography>
      {lines.map((line, index) => {
        const bad = error && !lineOk(line, productsOnly);
        return (
          <Stack
            key={index}
            direction={{ xs: "column", md: "row" }}
            spacing={1}
            sx={{ alignItems: { md: "center" } }}
          >
            <Autocomplete
              sx={{ flex: 2, minWidth: 0 }}
              size="small"
              options={options}
              getOptionLabel={(o) => o.name + (o.sku ? ` (${o.sku})` : "")}
              value={line.item_id ? (byId.get(line.item_id) ?? null) : null}
              disabled={Boolean(line.order_line_id)}
              onChange={(_, picked) =>
                update(index, {
                  item_id: picked?.id ?? null,
                  description: picked && !line.description ? picked.name : line.description,
                })
              }
              renderInput={(params) => (
                <TextField
                  {...params}
                  label={t("purchasing.item", { n: index + 1 })}
                  required={productsOnly}
                  error={bad && productsOnly && !line.item_id}
                />
              )}
            />
            {!productsOnly && (
              <TextField
                sx={{ flex: 2 }}
                size="small"
                label={t("purchasing.description", { n: index + 1 })}
                required
                value={line.description}
                error={bad && !line.description.trim()}
                onChange={(e) => update(index, { description: e.target.value })}
              />
            )}
            <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
              <TextField
                size="small"
                label={t("purchasing.quantity", { n: index + 1 })}
                value={line.quantity}
                error={bad && !(Number(line.quantity) > 0)}
                onChange={(e) => update(index, { quantity: cleanAmount(e.target.value, 3) })}
                sx={{ width: 110 }}
                slotProps={{ htmlInput: { dir: "ltr", inputMode: "decimal" } }}
              />
              <TextField
                size="small"
                label={t("purchasing.unitCost", { n: index + 1 })}
                value={line.unit_cost}
                error={bad && line.unit_cost === ""}
                onChange={(e) => update(index, { unit_cost: cleanAmount(e.target.value, 4) })}
                sx={{ width: 130 }}
                slotProps={{ htmlInput: { dir: "ltr", inputMode: "decimal" } }}
              />
              <Typography sx={{ minWidth: 90, textAlign: "left" }}>
                {formatMoney((Number(line.quantity) || 0) * (Number(line.unit_cost) || 0))}
              </Typography>
              <IconButton
                aria-label={t("purchasing.removeLine", { n: index + 1 })}
                disabled={lines.length === 1}
                onClick={() => onChange(lines.filter((_, i) => i !== index))}
              >
                <DeleteOutlined />
              </IconButton>
            </Stack>
          </Stack>
        );
      })}
      <Button
        startIcon={<AddIcon />}
        sx={{ alignSelf: "flex-start" }}
        onClick={() =>
          onChange([...lines, { item_id: null, description: "", quantity: "1", unit_cost: "" }])
        }
      >
        {t("purchasing.addLine")}
      </Button>
      <Typography sx={{ fontWeight: 600 }}>
        {t("purchasing.totalBeforeVat")}: {formatMoney(linesTotal(lines))}
      </Typography>
    </Stack>
  );
}
