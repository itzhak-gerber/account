import Card from "@mui/material/Card";
import Chip from "@mui/material/Chip";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import type { DocumentSummary } from "../../api/types";
import { formatDate, formatMoney } from "../../lib/money";

export function DocumentList({
  documents,
  empty,
}: {
  documents?: DocumentSummary[];
  empty: string;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  return (
    <Card variant="outlined">
      {documents?.length === 0 && (
        <Typography sx={{ p: 2 }} color="text.secondary">
          {empty}
        </Typography>
      )}
      <List disablePadding>
        {documents?.map((d) => (
          <ListItemButton key={d.id} divider onClick={() => void navigate(`/documents/${d.id}`)}>
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
              <Chip
                size="small"
                label={t(`docStatus.${d.status}`)}
                color={d.status === "issued" ? "success" : "default"}
                variant="outlined"
              />
            </Stack>
          </ListItemButton>
        ))}
      </List>
    </Card>
  );
}
