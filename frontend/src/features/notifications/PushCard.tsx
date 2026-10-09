import PhoneIphoneOutlined from "@mui/icons-material/PhoneIphoneOutlined";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { PushConfig, PushTestResult } from "../../api/types";
import { errorMessage } from "../../lib/errors";

const KEY = ["me", "push"];

function supported(): boolean {
  return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

/** iPhones and iPads deliver web push only to an app added to the home screen. */
function iosNeedsHomeScreen(): boolean {
  const ios = /iPhone|iPad|iPod/.test(navigator.userAgent);
  const standalone =
    window.matchMedia?.("(display-mode: standalone)").matches ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true;
  return ios && !standalone;
}

function keyBytes(base64url: string): Uint8Array<ArrayBuffer> {
  const base64 = base64url.replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64 + "=".repeat((4 - (base64.length % 4)) % 4));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

async function currentSubscription(): Promise<PushSubscription | null> {
  const registration = await navigator.serviceWorker.getRegistration();
  return (await registration?.pushManager.getSubscription()) ?? null;
}

/** Turns phone / desktop notifications on or off for the device in use. */
export function PushCard() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const config = useQuery({ queryKey: KEY, queryFn: () => api.get<PushConfig>("/me/push") });
  const [subscribed, setSubscribed] = useState<boolean | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const canPush = supported() && !iosNeedsHomeScreen();

  useEffect(() => {
    if (!canPush) return;
    void currentSubscription().then(async (s) => {
      setSubscribed(s !== null);
      // Re-send this device's registration: the server may have dropped it (expired, or
      // turned off from another session) while the browser still holds it.
      if (s) {
        const { endpoint, keys } = s.toJSON();
        await api.put("/me/push", { endpoint, keys }).catch(() => undefined);
        await queryClient.invalidateQueries({ queryKey: KEY });
      }
    });
  }, [canPush, queryClient]);

  const enable = useMutation({
    mutationFn: async () => {
      if ((await Notification.requestPermission()) !== "granted") throw new Error("denied");
      const registration = await navigator.serviceWorker.register("/sw.js");
      await navigator.serviceWorker.ready;
      // Always a fresh registration: an old one may have expired at the push service.
      await (await registration.pushManager.getSubscription())?.unsubscribe();
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: keyBytes(config.data!.public_key!),
      });
      const { endpoint, keys } = subscription.toJSON();
      await api.put("/me/push", { endpoint, keys });
    },
    onSuccess: async () => {
      setSubscribed(true);
      setProblem(null);
      setNotice(t("push.enabled"));
      await queryClient.invalidateQueries({ queryKey: KEY });
    },
  });
  const disable = useMutation({
    mutationFn: async () => {
      const subscription = await currentSubscription();
      if (!subscription) return;
      await api.post("/me/push/unsubscribe", { endpoint: subscription.endpoint });
      await subscription.unsubscribe();
    },
    onSuccess: async () => {
      setSubscribed(false);
      setNotice(null);
      await queryClient.invalidateQueries({ queryKey: KEY });
    },
  });
  const test = useMutation({
    mutationFn: () => api.post<PushTestResult>("/me/push/test"),
    onSuccess: async (result) => {
      if (result.sent > 0) {
        setNotice(t("push.testSent"));
      } else if (result.gone > 0) {
        // The push service dropped this registration: clear it here too, so "enable" shows.
        await (await currentSubscription())?.unsubscribe();
        setSubscribed(false);
        setNotice(null);
        setProblem(t("push.expired"));
      } else if (result.devices === 0) {
        setProblem(t("push.notRegistered"));
      } else {
        const codes = result.failures.join(", ");
        setProblem(codes ? `${t("push.notSent")} (${codes})` : t("push.notSent"));
      }
      await queryClient.invalidateQueries({ queryKey: KEY });
    },
  });

  const denied = "Notification" in window && Notification.permission === "denied";
  const error = enable.error ?? disable.error ?? test.error;
  let status: string;
  if (config.data && !config.data.public_key) status = t("push.unavailable");
  else if (iosNeedsHomeScreen()) status = t("push.iosHomeScreen");
  else if (!supported()) status = t("push.unsupported");
  else if (denied) status = t("push.denied");
  else status = subscribed ? t("push.onHere") : t("push.offHere");
  const ready = Boolean(config.data?.public_key) && canPush && !denied && subscribed !== null;

  return (
    <Card variant="outlined" id="push">
      <CardContent>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 1 }}>
          <PhoneIphoneOutlined color="primary" />
          <Typography variant="h6" component="h2">
            {t("push.title")}
          </Typography>
        </Stack>
        <Typography color="text.secondary" sx={{ mb: 2 }}>
          {t("push.help")}
        </Typography>
        <Typography sx={{ mb: 2 }}>{status}</Typography>
        {config.data && config.data.devices > 0 && (
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            {t("push.devices", { count: config.data.devices })}
          </Typography>
        )}
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error instanceof Error && error.message === "denied"
              ? t("push.denied")
              : errorMessage(t, error)}
          </Alert>
        )}
        {problem && (
          <Alert severity="warning" sx={{ mb: 2 }}>
            {problem}
          </Alert>
        )}
        {notice && (
          <Alert severity="success" sx={{ mb: 2 }} role="status">
            {notice}
          </Alert>
        )}
        {ready && (
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
            {subscribed ? (
              <>
                <Button
                  variant="outlined"
                  disabled={test.isPending}
                  onClick={() => {
                    setNotice(null);
                    setProblem(null);
                    test.mutate();
                  }}
                >
                  {t("push.test")}
                </Button>
                <Button color="error" disabled={disable.isPending} onClick={() => disable.mutate()}>
                  {t("push.disable")}
                </Button>
              </>
            ) : (
              <Button
                variant="contained"
                disabled={enable.isPending}
                onClick={() => enable.mutate()}
              >
                {t("push.enable")}
              </Button>
            )}
          </Stack>
        )}
      </CardContent>
    </Card>
  );
}
