import AddIcon from "@mui/icons-material/Add";
import SearchIcon from "@mui/icons-material/Search";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import Chip from "@mui/material/Chip";
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

import { api } from "../../api/client";
import type { Supplier } from "../../api/types";
import { SupplierDialog } from "./SupplierDialog";

export function SuppliersTab({ businessId, canEdit }: { businessId: string; canEdit: boolean }) {
  const { t } = useTranslation();
  const [search, setSearch] = useState("");
  const q = useDeferredValue(search);
  const [editing, setEditing] = useState<Supplier | null | "new">(null);
  const suppliers = useQuery({
    queryKey: ["business", businessId, "suppliers", q],
    queryFn: () =>
      api.get<Supplier[]>(
        `/businesses/${businessId}/suppliers?limit=200&include_archived=true&q=${encodeURIComponent(q)}`,
      ),
  });

  return (
    <Stack spacing={2}>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
        <TextField
          sx={{ flex: 1 }}
          placeholder={t("suppliers.search")}
          aria-label={t("suppliers.search")}
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
        {canEdit && (
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => setEditing("new")}>
            {t("suppliers.new")}
          </Button>
        )}
      </Stack>
      <Card variant="outlined">
        {suppliers.data?.length === 0 && (
          <Typography sx={{ p: 2 }} color="text.secondary">
            {t("suppliers.empty")}
          </Typography>
        )}
        <List disablePadding>
          {suppliers.data?.map((s) => (
            <ListItem key={s.id} disablePadding>
              <ListItemButton
                divider
                disabled={!canEdit}
                onClick={() => setEditing(s)}
                sx={{ gap: 1, flexWrap: "wrap" }}
              >
                <ListItemText
                  primary={s.name}
                  secondary={[s.contact_name, s.phone, s.email, s.tax_id]
                    .filter(Boolean)
                    .join(" · ")}
                />
                {s.is_archived && <Chip size="small" label={t("customers.archived")} />}
              </ListItemButton>
            </ListItem>
          ))}
        </List>
      </Card>
      {editing !== null && (
        <SupplierDialog
          businessId={businessId}
          supplier={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
        />
      )}
    </Stack>
  );
}
