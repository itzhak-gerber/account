import CheckCircleOutlined from "@mui/icons-material/CheckCircleOutlined";
import RemoveCircleOutlineOutlined from "@mui/icons-material/RemoveCircleOutlineOutlined";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import LinearProgress from "@mui/material/LinearProgress";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { ModuleName, PlanStatus, Usage } from "../../api/types";
import { errorMessage } from "../../lib/errors";
import { formatDate, formatMoney } from "../../lib/money";
import { PlanOffer } from "../plan/PlanOffer";

const MODULES: ModuleName[] = ["inventory", "scanning"];

function UsageRow({ label, usage, note }: { label: string; usage: Usage; note: string | null }) {
  const { t } = useTranslation();
  const share = usage.quota ? Math.min(100, (usage.used / usage.quota) * 100) : 0;
  return (
    <Stack spacing={0.5}>
      <Stack direction="row" sx={{ justifyContent: "space-between", gap: 2 }}>
        <Typography>{label}</Typography>
        <Typography>
          {usage.quota === null
            ? t("plan.usedUnlimited", { used: usage.used })
            : t("plan.usedOf", { used: usage.used, quota: usage.quota })}
        </Typography>
      </Stack>
      {usage.quota !== null && (
        <LinearProgress
          variant="determinate"
          value={share}
          color={share >= 100 ? "warning" : "primary"}
          aria-label={label}
        />
      )}
      {usage.over > 0 && (
        <Typography variant="body2" color="warning.main">
          {t("plan.over", { count: usage.over, amount: formatMoney(usage.over_amount) })}
        </Typography>
      )}
      {note && (
        <Typography variant="body2" color="text.secondary">
          {note}
        </Typography>
      )}
    </Stack>
  );
}

export function PlanTab({ businessId, canRequest }: { businessId: string; canRequest: boolean }) {
  const { t } = useTranslation();
  const [message, setMessage] = useState("");
  const status = useQuery({
    queryKey: ["business", businessId, "plan"],
    queryFn: () => api.get<PlanStatus>(`/businesses/${businessId}/plan`),
  });
  const request = useMutation({
    mutationFn: (planId: string | null) =>
      api.post(`/businesses/${businessId}/plan/upgrade-request`, { plan_id: planId, message }),
  });

  if (status.isError) return <Alert severity="error">{errorMessage(t, status.error)}</Alert>;
  if (!status.data) return null;
  const plan = status.data;
  const price = (value: string | null) =>
    value === null ? null : t("plan.overagePrice", { price: formatMoney(value) });

  return (
    <Stack spacing={3}>
      {plan.read_only && (
        <Alert severity="warning">
          <strong>{t("plan.readOnlyTitle")}.</strong> {t("plan.readOnlyBody")}
        </Alert>
      )}
      <Card variant="outlined">
        <CardContent>
          <Stack spacing={2}>
            <Typography variant="h6" component="h2">
              {t("plan.current")}
            </Typography>
            <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
              <Typography sx={{ fontWeight: 700 }}>{plan.name ?? t("plan.none")}</Typography>
              {plan.kind && <Chip size="small" label={t(`plan.kinds.${plan.kind}`)} />}
            </Stack>
            {!plan.read_only && (
              <Typography color="text.secondary">
                {plan.ends_on
                  ? t("plan.validUntil", { date: formatDate(plan.ends_on) })
                  : t("plan.noEnd")}
              </Typography>
            )}
            <Typography variant="subtitle2" component="h3">
              {t("plan.modules")}
            </Typography>
            <List dense disablePadding>
              <ListItem disableGutters>
                <CheckCircleOutlined color="success" sx={{ me: 1 }} aria-hidden />
                <ListItemText primary={t("plan.base")} />
              </ListItem>
              {MODULES.map((m) => {
                const included = plan.modules.includes(m);
                return (
                  <ListItem key={m} disableGutters>
                    {included ? (
                      <CheckCircleOutlined color="success" sx={{ me: 1 }} aria-hidden />
                    ) : (
                      <RemoveCircleOutlineOutlined color="disabled" sx={{ me: 1 }} aria-hidden />
                    )}
                    <ListItemText
                      primary={`${t(`plan.moduleNames.${m}`)} – ${
                        included ? t("plan.included") : t("plan.notIncluded")
                      }`}
                    />
                  </ListItem>
                );
              })}
            </List>
          </Stack>
        </CardContent>
      </Card>

      {!plan.read_only && (
        <Card variant="outlined">
          <CardContent>
            <Stack spacing={2}>
              <Typography variant="h6" component="h2">
                {t("plan.usageTitle")}
              </Typography>
              <UsageRow
                label={t("plan.documents")}
                usage={plan.documents}
                note={price(plan.document_overage_price)}
              />
              {plan.modules.includes("scanning") && (
                <UsageRow
                  label={t("plan.scans")}
                  usage={plan.scans}
                  note={price(plan.scan_overage_price) ?? t("plan.scansBlocked")}
                />
              )}
            </Stack>
          </CardContent>
        </Card>
      )}

      <Card variant="outlined">
        <CardContent>
          <Stack spacing={2}>
            <Typography variant="h6" component="h2">
              {t("plan.offers")}
            </Typography>
            <List disablePadding>
              {plan.available_plans.map((offer) => (
                <ListItem key={offer.id} disableGutters divider>
                  <ListItemText
                    primary={offer.name}
                    secondary={<PlanOffer plan={offer} />}
                    slotProps={{ secondary: { component: "div" } }}
                  />
                  {canRequest && (
                    <Button
                      size="small"
                      disabled={request.isPending || request.isSuccess}
                      onClick={() => request.mutate(offer.id)}
                    >
                      {t("plan.requestPlan")}
                    </Button>
                  )}
                </ListItem>
              ))}
            </List>
            {canRequest ? (
              <>
                <TextField
                  label={t("plan.message")}
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  multiline
                  minRows={2}
                  slotProps={{ htmlInput: { maxLength: 2000 } }}
                />
                <div>
                  <Button
                    variant="contained"
                    disabled={request.isPending || request.isSuccess}
                    onClick={() => request.mutate(null)}
                  >
                    {t("plan.request")}
                  </Button>
                </div>
              </>
            ) : (
              <Alert severity="info">{t("plan.askOwner")}</Alert>
            )}
            {request.isSuccess && <Alert severity="success">{t("plan.sent")}</Alert>}
            {request.isError && <Alert severity="error">{errorMessage(t, request.error)}</Alert>}
          </Stack>
        </CardContent>
      </Card>
    </Stack>
  );
}
