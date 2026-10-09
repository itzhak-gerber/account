import Alert from "@mui/material/Alert";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Switch from "@mui/material/Switch";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { ChannelPrefs, NotificationEvent, NotificationPreference } from "../../api/types";
import { errorMessage } from "../../lib/errors";

const CHANNELS: (keyof ChannelPrefs)[] = ["in_app", "push", "email"];
const PATH = "/me/notification-preferences";

export function PreferencesCard() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const prefs = useQuery({
    queryKey: ["me", "notification-preferences"],
    queryFn: () => api.get<NotificationPreference[]>(PATH),
  });
  const save = useMutation({
    mutationFn: (change: { event: NotificationEvent; channels: ChannelPrefs }) =>
      api.put<NotificationPreference[]>(PATH, {
        preferences: { [change.event]: change.channels },
      }),
    onSuccess: (data) => queryClient.setQueryData(["me", "notification-preferences"], data),
  });

  return (
    <Card variant="outlined" id="notifications">
      <CardContent>
        <Typography variant="h6" component="h2" gutterBottom>
          {t("notifications.prefsTitle")}
        </Typography>
        <Typography color="text.secondary" sx={{ mb: 2 }}>
          {t("notifications.prefsHelp")}
        </Typography>
        {save.isError && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {errorMessage(t, save.error)}
          </Alert>
        )}
        {prefs.data && (
          <Table size="small" aria-label={t("notifications.prefsTitle")}>
            <TableHead>
              <TableRow>
                <TableCell>{t("notifications.event")}</TableCell>
                {CHANNELS.map((c) => (
                  <TableCell key={c} align="center">
                    {t(`notifications.channels.${c}`)}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {prefs.data.map((p) => (
                <TableRow key={p.event}>
                  <TableCell>
                    <Typography variant="body2" sx={{ fontWeight: 500 }}>
                      {t(`notifications.events.${p.event}`)}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {t(`notifications.eventHelp.${p.event}`)}
                    </Typography>
                  </TableCell>
                  {CHANNELS.map((c) => (
                    <TableCell key={c} align="center">
                      <Switch
                        checked={p.channels[c]}
                        disabled={save.isPending}
                        slotProps={{
                          input: {
                            "aria-label": `${t(`notifications.events.${p.event}`)}: ${t(`notifications.channels.${c}`)}`,
                          },
                        }}
                        onChange={(e) =>
                          save.mutate({
                            event: p.event,
                            channels: { ...p.channels, [c]: e.target.checked },
                          })
                        }
                      />
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
          {t("notifications.pushLater")}
        </Typography>
      </CardContent>
    </Card>
  );
}
