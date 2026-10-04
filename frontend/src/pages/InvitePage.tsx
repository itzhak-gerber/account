import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Trans, useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router";

import { ApiError, api } from "../api/client";
import type { InvitationPreview } from "../api/types";
import { useSession } from "../auth/context";
import { errorMessage } from "../lib/errors";

export function InvitePage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const navigate = useNavigate();
  const { me, refresh, selectBusiness, logout } = useSession();

  const preview = useQuery({
    queryKey: ["invitation", token],
    queryFn: () =>
      api.get<InvitationPreview>(`/invitations/preview?token=${encodeURIComponent(token)}`),
    enabled: token.length >= 20,
    retry: false,
  });
  const accept = useMutation({
    mutationFn: () => api.post<{ business_id: string }>("/invitations/accept", { token }),
    onSuccess: async ({ business_id }) => {
      selectBusiness(business_id);
      await refresh();
      void navigate("/");
    },
  });

  const inv = preview.data;
  const wrongEmail = inv && inv.email.toLowerCase() !== me.user.email.toLowerCase();

  return (
    <Card variant="outlined" sx={{ maxWidth: 560 }}>
      <CardContent>
        <Stack spacing={2}>
          <Typography variant="h5" component="h1" sx={{ fontWeight: 700 }}>
            {t("invite.title")}
          </Typography>
          {(preview.isError || token.length < 20) && (
            <Alert severity="error">
              {preview.error instanceof ApiError && preview.error.status !== 404
                ? errorMessage(t, preview.error)
                : t("invite.notFound")}
            </Alert>
          )}
          {inv && (
            <>
              <Typography>
                <Trans
                  i18nKey="invite.body"
                  values={{
                    inviter: inv.invited_by_name,
                    business: inv.business_name,
                    role: t(`roles.${inv.role}`),
                  }}
                  components={{ b: <strong /> }}
                />
              </Typography>
              {inv.status !== "pending" && (
                <Alert severity="warning">
                  {t(`invite.status${inv.status[0].toUpperCase()}${inv.status.slice(1)}`)}
                </Alert>
              )}
              {inv.status === "pending" && wrongEmail && (
                <>
                  <Alert severity="warning">{t("invite.wrongEmail", { email: inv.email })}</Alert>
                  <Button variant="outlined" onClick={() => void logout()}>
                    {t("invite.switchAccount")}
                  </Button>
                </>
              )}
              {inv.status === "pending" && !wrongEmail && (
                <>
                  {accept.isError && (
                    <Alert severity="error">{errorMessage(t, accept.error)}</Alert>
                  )}
                  <Button
                    variant="contained"
                    size="large"
                    disabled={accept.isPending}
                    onClick={() => accept.mutate()}
                  >
                    {t("invite.accept")}
                  </Button>
                </>
              )}
            </>
          )}
        </Stack>
      </CardContent>
    </Card>
  );
}
