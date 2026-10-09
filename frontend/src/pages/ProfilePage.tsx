import CheckCircleOutlined from "@mui/icons-material/CheckCircleOutlined";
import ErrorOutlined from "@mui/icons-material/ErrorOutlined";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Divider from "@mui/material/Divider";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useMutation } from "@tanstack/react-query";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useLocation } from "react-router";

import { api, startLogin } from "../api/client";
import { useSession } from "../auth/context";
import { DevicesCard } from "../features/notifications/DevicesCard";
import { PreferencesCard } from "../features/notifications/PreferencesCard";
import { PushCard } from "../features/notifications/PushCard";
import { errorMessage } from "../lib/errors";

export function ProfilePage() {
  const { t } = useTranslation();
  const { me } = useSession();
  const { hash } = useLocation();
  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView({ behavior: "smooth" });
  }, [hash]);
  const logoutAll = useMutation({
    mutationFn: () => api.post<{ logout_url: string }>("/auth/logout-all"),
    onSuccess: ({ logout_url }) => window.location.assign(logout_url),
  });

  return (
    <Stack spacing={3} sx={{ maxWidth: 720 }}>
      <Typography variant="h4" component="h1" sx={{ fontWeight: 700 }}>
        {t("profile.title")}
      </Typography>
      <Card variant="outlined">
        <CardContent>
          <Typography variant="h6" component="h2" gutterBottom>
            {t("profile.account")}
          </Typography>
          <Typography>{me.user.full_name}</Typography>
          <Typography color="text.secondary" dir="ltr" sx={{ textAlign: "right" }}>
            {me.user.email}
          </Typography>
        </CardContent>
      </Card>
      <PreferencesCard />
      <PushCard />
      <Card variant="outlined">
        <CardContent>
          <Stack spacing={2}>
            <Typography variant="h6" component="h2">
              {t("profile.security")}
            </Typography>
            <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
              {me.mfa ? <CheckCircleOutlined color="success" /> : <ErrorOutlined color="warning" />}
              <Typography>{me.mfa ? t("mfa.enabled") : t("mfa.notEnabled")}</Typography>
            </Stack>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
              {!me.mfa && (
                <Button
                  variant="contained"
                  onClick={() => startLogin({ returnTo: "/profile", action: "CONFIGURE_TOTP" })}
                >
                  {t("mfa.setup")}
                </Button>
              )}
              <Button
                variant="outlined"
                onClick={() => startLogin({ returnTo: "/profile", action: "UPDATE_PASSWORD" })}
              >
                {t("profile.changePassword")}
              </Button>
            </Stack>
            <Divider />
            {logoutAll.isError && (
              <Alert severity="error">{errorMessage(t, logoutAll.error)}</Alert>
            )}
            <div>
              <Button color="error" variant="outlined" onClick={() => logoutAll.mutate()}>
                {t("profile.logoutAll")}
              </Button>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                {t("profile.logoutAllHelp")}
              </Typography>
            </div>
          </Stack>
        </CardContent>
      </Card>
      <DevicesCard />
    </Stack>
  );
}
