import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { Device } from "../../api/types";
import { formatDate } from "../../lib/money";

const KEY = ["me", "devices"];
const time = new Intl.DateTimeFormat("he-IL", { hour: "2-digit", minute: "2-digit" });
/** dd/mm/yyyy hh:mm in the viewer's time zone, like other dates in the app. */
const when = (iso: string) => {
  const at = new Date(iso);
  return `${formatDate(at.toLocaleDateString("en-CA"))} ${time.format(at)}`;
};

export function DevicesCard() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const devices = useQuery({ queryKey: KEY, queryFn: () => api.get<Device[]>("/me/devices") });
  const forget = useMutation({
    mutationFn: (id: string) => api.delete(`/me/devices/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
  });

  return (
    <Card variant="outlined">
      <CardContent>
        <Typography variant="h6" component="h2" gutterBottom>
          {t("devices.title")}
        </Typography>
        <Typography color="text.secondary">{t("devices.help")}</Typography>
        {devices.data?.length === 0 && (
          <Typography sx={{ mt: 2 }} color="text.secondary">
            {t("devices.empty")}
          </Typography>
        )}
        <List aria-label={t("devices.title")}>
          {devices.data?.map((d) => (
            <ListItem
              key={d.id}
              divider
              disableGutters
              secondaryAction={
                <Button
                  size="small"
                  color="error"
                  aria-label={t("devices.forgetLabel", { label: d.label })}
                  disabled={forget.isPending}
                  onClick={() => forget.mutate(d.id)}
                >
                  {t("devices.forget")}
                </Button>
              }
            >
              <ListItemText
                primary={
                  <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                    <span>{d.label}</span>
                    {d.current && (
                      <Chip size="small" color="success" label={t("devices.current")} />
                    )}
                  </Stack>
                }
                secondary={
                  <>
                    {t("devices.lastSeen", { date: when(d.last_seen_at) })}
                    {d.last_ip && (
                      <>
                        {" · "}
                        <span dir="ltr">{t("devices.ip", { ip: d.last_ip })}</span>
                      </>
                    )}
                  </>
                }
              />
            </ListItem>
          ))}
        </List>
      </CardContent>
    </Card>
  );
}
