import Chip from "@mui/material/Chip";
import { useTranslation } from "react-i18next";

import type { PaymentStatus } from "../../api/types";

export function PaymentChip({ status }: { status: PaymentStatus }) {
  const { t } = useTranslation();
  const color = status === "paid" ? "success" : status === "partial" ? "warning" : "error";
  return <Chip size="small" color={color} label={t(`paymentStatus.${status}`)} />;
}
