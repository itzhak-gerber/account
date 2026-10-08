import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useMutation } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import type { Business, BusinessInput, Membership } from "../api/types";
import { useSession } from "../auth/context";
import { BusinessForm } from "../features/settings/BusinessForm";
import { EMPTY_BUSINESS } from "../features/settings/emptyBusiness";
import { errorMessage } from "../lib/errors";
import { MfaRequiredPage } from "./MfaRequiredPage";

export function OnboardingPage() {
  const { t } = useTranslation();
  const { me, refresh, selectBusiness } = useSession();
  const input = useRef<HTMLInputElement>(null);
  const [logo, setLogo] = useState<File | null>(null);
  const [logoError, setLogoError] = useState(false);
  const preview = useMemo(() => (logo ? URL.createObjectURL(logo) : null), [logo]);
  useEffect(
    () => () => {
      if (preview) URL.revokeObjectURL(preview);
    },
    [preview],
  );

  const create = useMutation({
    mutationFn: async (input: BusinessInput) => {
      const membership = await api.post<Membership>("/businesses", input);
      if (logo) {
        // The business exists either way; a failed logo can be added later in the settings.
        await api
          .upload<Business>(`/businesses/${membership.business.id}/logo`, logo)
          .catch(() => undefined);
      }
      return membership;
    },
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
          <Stack
            direction={{ xs: "column", sm: "row" }}
            spacing={2}
            sx={{ alignItems: { sm: "center" }, mb: 3 }}
          >
            <Box
              sx={{
                width: 180,
                height: 72,
                border: 1,
                borderColor: "divider",
                borderRadius: 2,
                display: "grid",
                placeItems: "center",
                overflow: "hidden",
              }}
            >
              {preview ? (
                <img
                  src={preview}
                  alt={t("logo.title")}
                  style={{ maxWidth: "100%", maxHeight: "100%" }}
                />
              ) : (
                <Typography variant="body2" color="text.secondary">
                  {t("logo.none")}
                </Typography>
              )}
            </Box>
            <div>
              <input
                ref={input}
                type="file"
                accept="image/png,image/jpeg"
                hidden
                aria-label={t("logo.upload")}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  e.target.value = "";
                  if (!file) return;
                  const ok =
                    ["image/png", "image/jpeg"].includes(file.type) && file.size <= 2 << 20;
                  setLogoError(!ok);
                  if (ok) setLogo(file);
                }}
              />
              <Stack direction="row" spacing={1}>
                <Button variant="outlined" onClick={() => input.current?.click()}>
                  {logo ? t("logo.replace") : t("onboarding.logo")}
                </Button>
                {logo && (
                  <Button color="error" onClick={() => setLogo(null)}>
                    {t("logo.remove")}
                  </Button>
                )}
              </Stack>
              <Typography
                variant="body2"
                color={logoError ? "error" : "text.secondary"}
                role={logoError ? "alert" : undefined}
                sx={{ mt: 1 }}
              >
                {logoError ? t("onboarding.logoInvalid") : t("onboarding.logoHelp")}
              </Typography>
            </div>
          </Stack>
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
