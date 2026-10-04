import AddIcon from "@mui/icons-material/Add";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";

import { useSystemStatus } from "../api/system";
import { useSession } from "../auth/context";

function StatusRow({ label, value, ok }: { label: string; value: string; ok?: boolean }) {
  return (
    <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", py: 0.75 }}>
      <Typography color="text.secondary">{label}</Typography>
      {ok === undefined ? (
        <Typography dir="ltr">{value}</Typography>
      ) : (
        <Chip size="small" label={value} color={ok ? "success" : "error"} variant="outlined" />
      )}
    </Stack>
  );
}

export function DashboardPage() {
  const { t } = useTranslation();
  const { data, isPending, isError } = useSystemStatus();
  const { current } = useSession();

  return (
    <Stack spacing={3} sx={{ maxWidth: 960 }}>
      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={2}
        sx={{ justifyContent: "space-between", alignItems: { xs: "stretch", sm: "center" } }}
      >
        <Box>
          <Typography variant="h4" component="h1" sx={{ fontWeight: 700 }}>
            {t("dashboard.title")}
          </Typography>
          {current && (
            <Typography variant="h6" component="p" color="primary">
              {current.business.display_name} · {t("dashboard.yourRole")}:{" "}
              {t(`roles.${current.role}`)}
            </Typography>
          )}
          <Typography color="text.secondary">{t("dashboard.subtitle")}</Typography>
        </Box>
        <Tooltip title={t("common.comingSoon")}>
          <span>
            <Button variant="contained" size="large" startIcon={<AddIcon />} disabled fullWidth>
              {t("dashboard.newDocument")}
            </Button>
          </span>
        </Tooltip>
      </Stack>

      <Card variant="outlined" sx={{ maxWidth: 420 }}>
        <CardContent>
          <Typography variant="h6" component="h2" gutterBottom>
            {t("dashboard.systemStatus")}
          </Typography>
          {isPending && <Typography color="text.secondary">{t("dashboard.loading")}</Typography>}
          {isError && <Typography color="error">{t("dashboard.error")}</Typography>}
          {data && (
            <>
              <StatusRow
                label={t("dashboard.server")}
                value={t(`dashboard.${data.status}`)}
                ok={data.status === "ok"}
              />
              <StatusRow
                label={t("dashboard.database")}
                value={t(`dashboard.${data.database}`)}
                ok={data.database === "ok"}
              />
              <StatusRow label={t("dashboard.version")} value={data.version} />
            </>
          )}
        </CardContent>
      </Card>
    </Stack>
  );
}
