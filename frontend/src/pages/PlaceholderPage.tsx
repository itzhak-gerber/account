import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";

export function PlaceholderPage({ titleKey }: { titleKey: string }) {
  const { t } = useTranslation();
  return (
    <Stack spacing={1}>
      <Typography variant="h4" component="h1" sx={{ fontWeight: 700 }}>
        {t(titleKey)}
      </Typography>
      <Typography color="text.secondary">{t("common.comingSoon")}</Typography>
    </Stack>
  );
}
