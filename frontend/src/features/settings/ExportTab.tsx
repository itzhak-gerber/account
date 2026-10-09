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
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { DataExport } from "../../api/types";
import { errorMessage } from "../../lib/errors";
import { formatDate } from "../../lib/money";

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
  // Range of the uniform-format file (מבנה אחיד); empty: from the first document until today.
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const start = useMutation({
    mutationFn: () => api.post<DataExport>(base, { date_from: from || null, date_to: to || null }),
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
        <Typography variant="subtitle1" component="h3" sx={{ fontWeight: 600 }}>
          {t("exports.openformatTitle")}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {t("exports.openformatHelp")}
        </Typography>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ mb: 2 }}>
          <TextField
            type="date"
            size="small"
            label={t("exports.from")}
            value={from}
            onChange={(e) => setFrom(e.target.value)}
            slotProps={{ inputLabel: { shrink: true } }}
          />
          <TextField
            type="date"
            size="small"
            label={t("exports.to")}
            value={to}
            onChange={(e) => setTo(e.target.value)}
            slotProps={{ inputLabel: { shrink: true } }}
          />
        </Stack>
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
                          e.date_from || e.date_to
                            ? t("exports.range", {
                                from: e.date_from ? formatDate(e.date_from) : "…",
                                to: e.date_to ? formatDate(e.date_to) : "…",
                              })
                            : "",
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
