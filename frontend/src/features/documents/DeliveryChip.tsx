import Chip from "@mui/material/Chip";
import { useTranslation } from "react-i18next";

import type { DeliveryNoteStatus } from "../../api/types";

export function DeliveryChip({ status }: { status: DeliveryNoteStatus }) {
  const { t } = useTranslation();
  return (
    <Chip
      size="small"
      variant="outlined"
      color={status === "open" ? "warning" : "success"}
      label={t(`deliveryStatus.${status}`)}
    />
  );
}
