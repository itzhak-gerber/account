import SecurityOutlined from "@mui/icons-material/SecurityOutlined";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";

import { startLogin } from "../api/client";

export function MfaRequiredPage() {
  const { t } = useTranslation();
  const returnTo = window.location.pathname + window.location.search;
  return (
    <Card variant="outlined" sx={{ maxWidth: 560 }}>
      <CardContent>
        <Stack spacing={2}>
          <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
            <SecurityOutlined color="primary" />
            <Typography variant="h5" component="h1" sx={{ fontWeight: 700 }}>
              {t("mfa.title")}
            </Typography>
          </Stack>
          <Typography>{t("mfa.explainOwner")}</Typography>
          <Typography color="text.secondary">{t("mfa.steps")}</Typography>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <Button
              variant="contained"
              onClick={() => startLogin({ returnTo, action: "CONFIGURE_TOTP" })}
            >
              {t("mfa.setup")}
            </Button>
            <Button variant="text" onClick={() => startLogin({ returnTo, reauth: true })}>
              {t("mfa.signInAgain")}
            </Button>
          </Stack>
        </Stack>
      </CardContent>
    </Card>
  );
}
