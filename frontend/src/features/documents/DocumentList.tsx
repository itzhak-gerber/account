import Card from "@mui/material/Card";
import Chip from "@mui/material/Chip";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";
import { Link as RouterLink } from "react-router";

import type { DocumentSummary } from "../../api/types";
import { formatDate, formatMoney } from "../../lib/money";
import { DeliveryChip } from "./DeliveryChip";
import { PaymentChip } from "./PaymentChip";

export function DocumentList({
  documents,
  empty,
}: {
  documents?: DocumentSummary[];
  empty: string;
}) {
  const { t } = useTranslation();
  return (
    <Card variant="outlined">
      {documents?.length === 0 && (
        <Typography sx={{ p: 2 }} color="text.secondary">
          {empty}
        </Typography>
      )}
      <List disablePadding>
        {documents?.map((d) => (
          <ListItem key={d.id} disablePadding>
            <ListItemButton divider component={RouterLink} to={`/documents/${d.id}`}>
              <ListItemText
                primary={
                  <>
                    {t(`docTypes.${d.type}`)}
                    {d.number !== null && ` ${t("documents.number")} ${d.number}`}
                  </>
                }
                secondary={`${d.customer_name || "—"} · ${formatDate(d.issue_date)}`}
              />
              <Stack sx={{ alignItems: "flex-end", gap: 0.5 }}>
                <Typography sx={{ fontWeight: 500 }}>{formatMoney(d.total)}</Typography>
                {d.delivery_status ? (
                  <DeliveryChip status={d.delivery_status} />
                ) : d.payment_status && d.payment_status !== "paid" ? (
                  <PaymentChip status={d.payment_status} />
                ) : (
                  <Chip
                    size="small"
                    label={t(`docStatus.${d.status}`)}
                    color={d.status === "issued" ? "success" : "default"}
                    variant="outlined"
                  />
                )}
              </Stack>
            </ListItemButton>
          </ListItem>
        ))}
      </List>
    </Card>
  );
}
