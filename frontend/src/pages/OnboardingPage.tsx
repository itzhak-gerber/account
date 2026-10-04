import Alert from "@mui/material/Alert";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import type { BusinessInput, Membership } from "../api/types";
import { useSession } from "../auth/context";
import { BusinessForm } from "../features/settings/BusinessForm";
import { EMPTY_BUSINESS } from "../features/settings/emptyBusiness";
import { errorMessage } from "../lib/errors";
import { MfaRequiredPage } from "./MfaRequiredPage";

export function OnboardingPage() {
  const { t } = useTranslation();
  const { me, refresh, selectBusiness } = useSession();
  const create = useMutation({
    mutationFn: (input: BusinessInput) => api.post<Membership>("/businesses", input),
    onSuccess: async (membership) => {
      selectBusiness(membership.business.id);
      await refresh();
    },
  });

  // Creating a business makes you its owner, and owners must use two-factor authentication.
  if (!me.mfa) return <MfaRequiredPage />;

  return (
    <Stack spacing={3} sx={{ maxWidth: 900 }}>
      <div>
        <Typography variant="h4" component="h1" sx={{ fontWeight: 700 }}>
          {t("onboarding.title")}
        </Typography>
        <Typography color="text.secondary">{t("onboarding.subtitle")}</Typography>
      </div>
      <Card variant="outlined">
        <CardContent>
          {create.isError && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {errorMessage(t, create.error)}
            </Alert>
          )}
          <BusinessForm
            initial={EMPTY_BUSINESS}
            submitLabel={t("onboarding.create")}
            busy={create.isPending}
            onSubmit={(value) => create.mutate(value)}
          />
        </CardContent>
      </Card>
      <Typography variant="body2" color="text.secondary">
        {t("onboarding.pendingInvite")}
      </Typography>
    </Stack>
  );
}
