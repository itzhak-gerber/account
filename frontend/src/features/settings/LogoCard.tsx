import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { Business } from "../../api/types";
import { useSession } from "../../auth/context";
import { errorMessage } from "../../lib/errors";

export function LogoCard({ business, canEdit }: { business: Business; canEdit: boolean }) {
  const { t } = useTranslation();
  const { refresh } = useSession();
  const input = useRef<HTMLInputElement>(null);
  const [version, setVersion] = useState(0);
  const url = `/businesses/${business.id}/logo`;

  const logo = useQuery({
    queryKey: ["business", business.id, "logo", version],
    queryFn: async () => {
      const response = await fetch(`/api/v1${url}`, { credentials: "same-origin" });
      return response.ok ? URL.createObjectURL(await response.blob()) : null;
    },
    enabled: business.has_logo,
  });
  useEffect(() => {
    const objectUrl = logo.data;
    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [logo.data]);

  const upload = useMutation({
    mutationFn: (file: File) => api.upload<Business>(url, file),
    onSuccess: async () => {
      setVersion((v) => v + 1);
      await refresh();
    },
  });
  const remove = useMutation({
    mutationFn: () => api.delete(url),
    onSuccess: async () => {
      setVersion((v) => v + 1);
      await refresh();
    },
  });
  const error = upload.error ?? remove.error;

  return (
    <Card variant="outlined">
      <CardContent>
        <Typography variant="h6" component="h2" gutterBottom>
          {t("logo.title")}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {t("logo.help")}
        </Typography>
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {errorMessage(t, error)}
          </Alert>
        )}
        <Stack
          direction={{ xs: "column", sm: "row" }}
          spacing={2}
          sx={{ alignItems: { sm: "center" } }}
        >
          <Box
            sx={{
              width: 220,
              height: 90,
              border: 1,
              borderColor: "divider",
              borderRadius: 2,
              display: "grid",
              placeItems: "center",
              bgcolor: "background.default",
              overflow: "hidden",
            }}
          >
            {business.has_logo && logo.data ? (
              <img
                src={logo.data}
                alt={t("logo.title")}
                style={{ maxWidth: "100%", maxHeight: "100%" }}
              />
            ) : (
              <Typography variant="body2" color="text.secondary">
                {t("logo.none")}
              </Typography>
            )}
          </Box>
          {canEdit && (
            <Stack direction="row" spacing={1}>
              <input
                ref={input}
                type="file"
                accept="image/png,image/jpeg"
                hidden
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) upload.mutate(file);
                  e.target.value = "";
                }}
              />
              <Button
                variant="outlined"
                disabled={upload.isPending}
                onClick={() => input.current?.click()}
              >
                {business.has_logo ? t("logo.replace") : t("logo.upload")}
              </Button>
              {business.has_logo && (
                <Button color="error" disabled={remove.isPending} onClick={() => remove.mutate()}>
                  {t("logo.remove")}
                </Button>
              )}
            </Stack>
          )}
        </Stack>
      </CardContent>
    </Card>
  );
}
