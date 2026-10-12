import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
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
import type { ModuleName, PlanStatus } from "../../api/types";
import { useSession } from "../../auth/context";
import { can } from "../../auth/permissions";
import { errorMessage } from "../../lib/errors";
import { PlanOffer } from "./PlanOffer";

/** What a module does, the plans that include it, and a request to upgrade. */
export function UpgradeDialog({ module, onClose }: { module: ModuleName; onClose: () => void }) {
  const { t } = useTranslation();
  const { current } = useSession();
  const businessId = current!.business.id;
  const canRequest = can(current?.role, "manageBusiness");
  const [message, setMessage] = useState("");
  const status = useQuery({
    queryKey: ["business", businessId, "plan"],
    queryFn: () => api.get<PlanStatus>(`/businesses/${businessId}/plan`),
  });
  const request = useMutation({
    mutationFn: (planId: string | null) =>
      api.post(`/businesses/${businessId}/plan/upgrade-request`, {
        module,
        plan_id: planId,
        message,
      }),
  });
  const offers = (status.data?.available_plans ?? []).filter((p) => p.modules.includes(module));
  const name = t(`plan.moduleNames.${module}`);

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{t("plan.upgradeTitle", { module: name })}</DialogTitle>
      <DialogContent>
        <Stack spacing={2}>
          <Typography>{t(`plan.moduleHelp.${module}`)}</Typography>
          <Typography variant="subtitle1" component="h3" sx={{ fontWeight: 700 }}>
            {t("plan.plansWith")}
          </Typography>
          {status.isSuccess && offers.length === 0 && (
            <Typography color="text.secondary">{t("plan.noPlansWith")}</Typography>
          )}
          <List disablePadding>
            {offers.map((plan) => (
              <ListItem key={plan.id} disableGutters divider>
                <ListItemText
                  primary={plan.name}
                  secondary={<PlanOffer plan={plan} />}
                  slotProps={{ secondary: { component: "div" } }}
                />
                {canRequest && (
                  <Button
                    size="small"
                    disabled={request.isPending || request.isSuccess}
                    onClick={() => request.mutate(plan.id)}
                  >
                    {t("plan.requestPlan")}
                  </Button>
                )}
              </ListItem>
            ))}
          </List>
          {canRequest ? (
            <TextField
              label={t("plan.message")}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              multiline
              minRows={2}
              slotProps={{ htmlInput: { maxLength: 2000 } }}
            />
          ) : (
            <Alert severity="info">{t("plan.askOwner")}</Alert>
          )}
          {request.isSuccess && <Alert severity="success">{t("plan.sent")}</Alert>}
          {request.isError && <Alert severity="error">{errorMessage(t, request.error)}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t("plan.close")}</Button>
        {canRequest && (
          <Button
            variant="contained"
            disabled={request.isPending || request.isSuccess}
            onClick={() => request.mutate(null)}
          >
            {t("plan.request")}
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
}
