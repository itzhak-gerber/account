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
import type { Item, KitComponent } from "../../api/types";
import { cleanAmount } from "../../lib/amount";

interface Props {
  businessId: string;
  kitId: string | null;
  components: KitComponent[];
  error: boolean;
  onChange: (components: KitComponent[]) => void;
}

/** The items a sales kit is made of (plain products and services; no kit inside a kit). */
export function KitComponentsEditor({ businessId, kitId, components, error, onChange }: Props) {
  const { t } = useTranslation();
  const items = useQuery({
    queryKey: ["business", businessId, "items", ""],
    queryFn: () => api.get<Item[]>(`/businesses/${businessId}/items?limit=200&q=`),
  });
  const options = (items.data ?? []).filter((i) => i.item_type !== "kit" && i.id !== kitId);
  const byId = new Map(options.map((i) => [i.id, i]));
  const update = (index: number, patch: Partial<KitComponent>) =>
    onChange(components.map((c, i) => (i === index ? { ...c, ...patch } : c)));

  return (
    <Stack spacing={1.5} component="fieldset" sx={{ border: 0, p: 0, m: 0 }}>
      <Typography component="legend" sx={{ fontWeight: 500, mb: 0.5 }}>
        {t("items.components")}
      </Typography>
      <Typography variant="body2" color={error ? "error" : "text.secondary"}>
        {t("items.componentsHelp")}
      </Typography>
      {components.map((component, index) => (
        <Stack key={index} direction="row" spacing={1} sx={{ alignItems: "center" }}>
          <Autocomplete
            sx={{ flex: 1 }}
            size="small"
            options={options.filter(
              (o) => o.id === component.item_id || !components.some((c) => c.item_id === o.id),
            )}
            getOptionLabel={(o) => o.name + (o.sku ? ` (${o.sku})` : "")}
            value={byId.get(component.item_id) ?? null}
            onChange={(_, picked) => update(index, { item_id: picked?.id ?? "" })}
            renderInput={(params) => (
              <TextField
                {...params}
                label={t("items.component", { n: index + 1 })}
                error={error && !component.item_id}
              />
            )}
          />
          <TextField
            size="small"
            label={t("editor.quantity")}
            value={component.quantity}
            onChange={(e) => update(index, { quantity: cleanAmount(e.target.value, 3) })}
            error={error && !(Number(component.quantity) > 0)}
            sx={{ width: 110 }}
            slotProps={{ htmlInput: { dir: "ltr", inputMode: "decimal" } }}
          />
          <IconButton
            aria-label={t("items.removeComponent", { n: index + 1 })}
            onClick={() => onChange(components.filter((_, i) => i !== index))}
          >
            <DeleteOutlined />
          </IconButton>
        </Stack>
      ))}
      <Button
        startIcon={<AddIcon />}
        sx={{ alignSelf: "flex-start" }}
        onClick={() => onChange([...components, { item_id: "", quantity: "1" }])}
      >
        {t("items.addComponent")}
      </Button>
    </Stack>
  );
}
