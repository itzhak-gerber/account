import AddIcon from "@mui/icons-material/Add";
import SearchIcon from "@mui/icons-material/Search";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import InputAdornment from "@mui/material/InputAdornment";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useQuery } from "@tanstack/react-query";
import { useDeferredValue, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import type { Item } from "../api/types";
import { useSession } from "../auth/context";
import { can } from "../auth/permissions";
import { ItemDialog } from "../features/catalog/ItemDialog";
import { formatMoney } from "../lib/money";

export function ItemsPage() {
  const { t } = useTranslation();
  const { current } = useSession();
  const businessId = current!.business.id;
  const [search, setSearch] = useState("");
  const q = useDeferredValue(search);
  const [editing, setEditing] = useState<Item | null | "new">(null);
  const canEdit = can(current?.role, "manageCatalog");

  const items = useQuery({
    queryKey: ["business", businessId, "items", q],
    queryFn: () =>
      api.get<Item[]>(`/businesses/${businessId}/items?limit=200&q=${encodeURIComponent(q)}`),
  });

  return (
    <Stack spacing={3} sx={{ maxWidth: 960 }}>
      <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", gap: 2 }}>
        <Typography variant="h4" component="h1" sx={{ fontWeight: 700 }}>
          {t("items.title")}
        </Typography>
        {canEdit && (
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => setEditing("new")}>
            {t("items.new")}
          </Button>
        )}
      </Stack>
      <TextField
        placeholder={t("items.search")}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        slotProps={{
          input: {
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon />
              </InputAdornment>
            ),
          },
        }}
      />
      <Card variant="outlined">
        {items.data?.length === 0 && (
          <Typography sx={{ p: 2 }} color="text.secondary">
            {t("items.empty")}
          </Typography>
        )}
        <List disablePadding>
          {items.data?.map((item) => (
            <ListItem key={item.id} disablePadding>
              <ListItemButton divider onClick={() => canEdit && setEditing(item)}>
                <ListItemText
                  primary={item.name}
                  secondary={[
                    t(`items.types.${item.item_type}`),
                    item.sku,
                    t(`vatTypes.${item.vat_type}`),
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                />
                <Typography sx={{ fontWeight: 500 }}>
                  {formatMoney(item.unit_price)}
                  {item.unit_of_measure && ` / ${item.unit_of_measure}`}
                </Typography>
              </ListItemButton>
            </ListItem>
          ))}
        </List>
      </Card>
      {editing !== null && (
        <ItemDialog
          open
          businessId={businessId}
          item={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
        />
      )}
    </Stack>
  );
}
