import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router";

import { api } from "../../api/client";
import type { ItaStatus } from "../../api/types";
import { errorMessage } from "../../lib/errors";
import { formatDate, formatMoney } from "../../lib/money";

/** Connecting the business to the tax authority, for allocation numbers on tax invoices. */
export function ItaTab({ businessId, canManage }: { businessId: string; canManage: boolean }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [params] = useSearchParams();
  const returned = params.get("ita");
  const key = ["business", businessId, "ita"];
  const status = useQuery({
    queryKey: key,
    queryFn: () => api.get<ItaStatus>(`/businesses/${businessId}/ita`),
  });
  const connect = useMutation({
    mutationFn: () => api.post<{ url: string }>(`/businesses/${businessId}/ita/connect`),
    // The owner signs in at the tax authority, then comes back to this tab.
    onSuccess: ({ url }) => window.location.assign(url),
  });
  const disconnect = useMutation({
    mutationFn: () => api.delete(`/businesses/${businessId}/ita`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: key }),
  });
  const s = status.data;

  return (
    <Card variant="outlined">
      <CardContent>
        <Stack spacing={2}>
          <Typography variant="h6" component="h2">
            {t("ita.title")}
          </Typography>
          <Typography color="text.secondary">{t("ita.help")}</Typography>
          {s?.threshold && (
            <Typography variant="body2">
              {t("ita.threshold", { amount: formatMoney(s.threshold) })}
            </Typography>
          )}
          {returned === "connected" && <Alert severity="success">{t("ita.connectedNow")}</Alert>}
          {(returned === "failed" || returned === "cancelled") && (
            <Alert severity="error">{t(`ita.${returned}`)}</Alert>
          )}
          {(connect.isError || disconnect.isError) && (
            <Alert severity="error">{errorMessage(t, connect.error ?? disconnect.error)}</Alert>
          )}
          {s && !s.enabled && <Alert severity="info">{t("ita.notEnabled")}</Alert>}
          {s?.enabled && (
            <>
              {s.environment === "sandbox" && <Alert severity="warning">{t("ita.sandbox")}</Alert>}
              <Typography sx={{ fontWeight: 600 }}>
                {s.connected
                  ? t("ita.connected", { date: formatDate(s.connected_at) })
                  : t("ita.notConnected")}
              </Typography>
              {s.connected && s.expires_at && (
                <Typography variant="body2" color="text.secondary">
                  {t("ita.expires", { date: formatDate(s.expires_at) })}
                </Typography>
              )}
              {canManage && (
                <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                  <Button
                    variant="contained"
                    disabled={connect.isPending}
                    onClick={() => connect.mutate()}
                  >
                    {s.connected ? t("ita.reconnect") : t("ita.connect")}
                  </Button>
                  {s.connected && (
                    <Button
                      color="error"
                      disabled={disconnect.isPending}
                      onClick={() => disconnect.mutate()}
                    >
                      {t("ita.disconnect")}
                    </Button>
                  )}
                </Stack>
              )}
              {canManage && !s.connected && (
                <Typography variant="body2" color="text.secondary">
                  {t("ita.connectHelp")}
                </Typography>
              )}
            </>
          )}
        </Stack>
      </CardContent>
    </Card>
  );
}
