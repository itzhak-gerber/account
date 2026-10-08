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

import { api } from "../api/client";
import type { Customer } from "../api/types";
import { useSession } from "../auth/context";
import { can } from "../auth/permissions";
import { CustomerDialog } from "../features/catalog/CustomerDialog";

export function CustomersPage() {
  const { t } = useTranslation();
  const { current } = useSession();
  const businessId = current!.business.id;
  const [search, setSearch] = useState("");
  const q = useDeferredValue(search);
  const [editing, setEditing] = useState<Customer | null | "new">(null);
  const canEdit = can(current?.role, "manageCatalog");

  const customers = useQuery({
    queryKey: ["business", businessId, "customers", q],
    queryFn: () =>
      api.get<Customer[]>(
        `/businesses/${businessId}/customers?limit=200&q=${encodeURIComponent(q)}`,
      ),
  });

  return (
    <Stack spacing={3} sx={{ maxWidth: 960 }}>
      <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", gap: 2 }}>
        <Typography variant="h4" component="h1" sx={{ fontWeight: 700 }}>
          {t("customers.title")}
        </Typography>
        {canEdit && (
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => setEditing("new")}>
            {t("customers.new")}
          </Button>
        )}
      </Stack>
      <TextField
        placeholder={t("customers.search")}
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
        {customers.data?.length === 0 && (
          <Typography sx={{ p: 2 }} color="text.secondary">
            {t("customers.empty")}
          </Typography>
        )}
        <List disablePadding>
          {customers.data?.map((c) => (
            <ListItem key={c.id} disablePadding>
              <ListItemButton
                divider
                onClick={() => canEdit && setEditing(c)}
                sx={{ gap: 1, flexWrap: "wrap" }}
              >
                <ListItemText
                  primary={c.name}
                  secondary={[c.tax_id, c.phone, c.email, c.address_city]
                    .filter(Boolean)
                    .join(" · ")}
                />
                {c.is_archived && <Chip size="small" label={t("customers.archived")} />}
              </ListItemButton>
            </ListItem>
          ))}
        </List>
      </Card>
      {editing !== null && (
        <CustomerDialog
          open
          businessId={businessId}
          customer={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
        />
      )}
    </Stack>
  );
}
