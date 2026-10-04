import LockOutlined from "@mui/icons-material/LockOutlined";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";

import { startLogin } from "../api/client";

export function LandingPage() {
  const { t } = useTranslation();
  const authError = new URLSearchParams(window.location.search).get("auth_error");

  return (
    <Box
      sx={{
        minHeight: "100dvh",
        display: "grid",
        placeItems: "center",
        p: 2,
        background: "linear-gradient(160deg, #eef2ff 0%, #f5f7fb 60%)",
      }}
    >
      <Stack spacing={3} sx={{ maxWidth: 520, textAlign: "center", alignItems: "center" }}>
        <Typography variant="h3" component="h1" sx={{ fontWeight: 700, color: "primary.main" }}>
          {t("app.name")}
        </Typography>
        <Typography variant="h5" component="p" sx={{ fontWeight: 500 }}>
          {t("landing.title")}
        </Typography>
        <Typography color="text.secondary">{t("landing.subtitle")}</Typography>
        {authError && (
          <Alert severity="error" sx={{ width: "100%" }}>
            {t(`errors.${authError}`, { defaultValue: t("errors.login_failed") })}
          </Alert>
        )}
        <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ width: "100%" }}>
          <Button variant="contained" size="large" fullWidth onClick={() => startLogin({})}>
            {t("landing.login")}
          </Button>
          <Button
            variant="outlined"
            size="large"
            fullWidth
            onClick={() => startLogin({ register: true })}
          >
            {t("landing.register")}
          </Button>
        </Stack>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center", color: "text.secondary" }}>
          <LockOutlined fontSize="small" />
          <Typography variant="body2">{t("landing.secure")}</Typography>
        </Stack>
      </Stack>
    </Box>
  );
}
