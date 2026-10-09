import DownloadOutlined from "@mui/icons-material/DownloadOutlined";
import Alert from "@mui/material/Alert";
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
import type { DataExport } from "../../api/types";
import { errorMessage } from "../../lib/errors";

function size(bytes: number | null): string {
  if (!bytes) return "";
  return bytes > 1_000_000
    ? `${(bytes / 1_000_000).toFixed(1)} MB`
    : `${Math.ceil(bytes / 1000)} KB`;
}

const when = (iso: string) => new Date(iso).toLocaleString("he-IL");

/** Download everything: every issued document (PDF copy) and all data, as one ZIP. */
export function ExportTab({ businessId }: { businessId: string }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const base = `/businesses/${businessId}/exports`;
  const key = ["business", businessId, "exports"];
  const exports = useQuery({
    queryKey: key,
    queryFn: () => api.get<DataExport[]>(base),
    // Refresh while one is being prepared.
    refetchInterval: (query) =>
      query.state.data?.some((e) => e.status === "pending") ? 3000 : false,
  });
  const start = useMutation({
    mutationFn: () => api.post<DataExport>(base),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: key }),
  });
  const pending = exports.data?.some((e) => e.status === "pending") ?? false;

  return (
    <Card variant="outlined">
      <CardContent>
        <Typography variant="h6" component="h2" gutterBottom>
          {t("exports.title")}
        </Typography>
        <Typography color="text.secondary" sx={{ mb: 1 }}>
          {t("exports.help")}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {t("exports.retention")}
        </Typography>
        {start.isError && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {errorMessage(t, start.error)}
          </Alert>
        )}
        <Button
          variant="contained"
          disabled={start.isPending || pending}
          onClick={() => start.mutate()}
        >
          {pending ? t("exports.preparing") : t("exports.start")}
        </Button>

        {exports.data && exports.data.length > 0 && (
          <List aria-label={t("exports.recent")} sx={{ mt: 2 }}>
            {exports.data.map((e) => (
              <ListItem
                key={e.id}
                divider
                disableGutters
                secondaryAction={
                  e.downloadable ? (
                    <Button
                      href={`/api/v1${base}/${e.id}/download`}
                      startIcon={<DownloadOutlined />}
                    >
                      {t("exports.download")}
                    </Button>
                  ) : undefined
                }
              >
                <ListItemText
                  primary={
                    <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                      <span>{when(e.created_at)}</span>
                      <Chip
                        size="small"
                        variant="outlined"
                        color={
                          e.status === "ready"
                            ? "success"
                            : e.status === "failed"
                              ? "error"
                              : "default"
                        }
                        label={t(
                          `exports.status.${e.downloadable || e.status !== "ready" ? e.status : "expired"}`,
                        )}
                      />
                    </Stack>
                  }
                  secondary={
                    e.status === "ready"
                      ? [
                          t("exports.documents", { count: e.documents ?? 0 }),
                          size(e.size),
                          e.downloadable && e.expires_at
                            ? t("exports.until", { date: when(e.expires_at) })
                            : "",
                        ]
                          .filter(Boolean)
                          .join(" · ")
                      : undefined
                  }
                />
              </ListItem>
            ))}
          </List>
        )}
      </CardContent>
    </Card>
  );
}
