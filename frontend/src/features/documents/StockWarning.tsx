import Alert from "@mui/material/Alert";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { LineInput, Stock } from "../../api/types";

interface Props {
  businessId: string;
  lines: LineInput[];
}

/**
 * Warns when an invoice sells more than is in stock. Issuing is still allowed (stock may go
 * negative); kits count against their components.
 */
export function StockWarning({ businessId, lines }: Props) {
  const { t } = useTranslation();
  const { data: stock } = useQuery({
    queryKey: ["business", businessId, "inventory"],
    queryFn: () => api.get<Stock>(`/businesses/${businessId}/inventory`),
  });
  if (!stock) return null;

  const tracked = new Map(stock.items.map((s) => [s.item.id, s]));
  const kits = new Map(stock.kits.map((k) => [k.item.id, k.item]));
  const needed = new Map<string, number>();
  const add = (id: string, quantity: number) => {
    if (tracked.has(id)) needed.set(id, (needed.get(id) ?? 0) + quantity);
  };
  for (const line of lines) {
    if (!line.item_id) continue;
    const quantity = Number(line.quantity || "1");
    if (!(quantity > 0)) continue;
    const kit = kits.get(line.item_id);
    if (kit) for (const c of kit.components) add(c.item_id, quantity * Number(c.quantity));
    else add(line.item_id, quantity);
  }

  const short = [...needed]
    .map(([id, quantity]) => ({ row: tracked.get(id)!, quantity }))
    .filter(({ row, quantity }) => quantity > Number(row.quantity));
  if (short.length === 0) return null;

  return (
    <Alert severity="warning" sx={{ mt: 1 }}>
      {t("editor.stockShort")}
      <ul style={{ margin: 0 }}>
        {short.map(({ row, quantity }) => (
          <li key={row.item.id}>
            {t("editor.stockShortLine", {
              name: row.item.name,
              needed: Number(quantity.toFixed(3)),
              available: Number(row.quantity),
            })}
          </li>
        ))}
      </ul>
    </Alert>
  );
}
