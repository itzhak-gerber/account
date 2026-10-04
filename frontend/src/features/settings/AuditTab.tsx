import Card from "@mui/material/Card";
import Chip from "@mui/material/Chip";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import Typography from "@mui/material/Typography";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { AuditEntry } from "../../api/types";

const dateFormat = new Intl.DateTimeFormat("he-IL", { dateStyle: "short", timeStyle: "short" });

export function AuditTab({ businessId }: { businessId: string }) {
  const { t } = useTranslation();
  const entries = useQuery({
    queryKey: ["business", businessId, "audit"],
    queryFn: () => api.get<AuditEntry[]>(`/businesses/${businessId}/audit-log?limit=100`),
  });

  return (
    <Card variant="outlined">
      {entries.data?.length === 0 && (
        <Typography sx={{ p: 2 }} color="text.secondary">
          {t("audit.empty")}
        </Typography>
      )}
      <List disablePadding>
        {entries.data?.map((e) => (
          <ListItem key={e.id} divider sx={{ gap: 1, flexWrap: "wrap" }}>
            <ListItemText
              primary={t(`audit.actions.${e.action}`, { defaultValue: e.action })}
              secondary={
                <>
                  <span dir="ltr">{e.actor_email}</span> ·{" "}
                  {dateFormat.format(new Date(e.created_at))}
                </>
              }
            />
            <Chip size="small" variant="outlined" label={t(`audit.channels.${e.actor_channel}`)} />
          </ListItem>
        ))}
      </List>
    </Card>
  );
}
