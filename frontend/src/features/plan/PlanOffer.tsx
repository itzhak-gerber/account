import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";

import type { Plan } from "../../api/types";
import { formatMoney } from "../../lib/money";

/** A plan as offered: price for the period, modules and monthly quotas. */
export function PlanOffer({ plan }: { plan: Plan }) {
  const { t } = useTranslation();
  const price = plan.current_price ?? plan.price;
  const quota = (count: number | null) =>
    count === null ? t("plan.unlimited") : t("plan.perMonth", { count });
  return (
    <Stack component="span" spacing={0.25}>
      <Typography component="span" variant="body2">
        {t("plan.perPeriod", { price: formatMoney(price), months: plan.duration_months })}
      </Typography>
      {plan.description && (
        <Typography component="span" variant="body2" color="text.secondary">
          {plan.description}
        </Typography>
      )}
      <Typography component="span" variant="body2" color="text.secondary">
        {[
          ...plan.modules.map((m) => t(`plan.moduleNames.${m}`)),
          `${t("plan.documents")}: ${quota(plan.documents_per_month)}`,
          ...(plan.modules.includes("scanning")
            ? [`${t("plan.scans")}: ${quota(plan.scans_per_month)}`]
            : []),
        ].join(" · ")}
      </Typography>
    </Stack>
  );
}
