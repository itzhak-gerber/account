import Alert from "@mui/material/Alert";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router";

import { useSession } from "../auth/context";
import { can } from "../auth/permissions";
import { InvoicesTab } from "../features/purchasing/InvoicesTab";
import { OrdersTab } from "../features/purchasing/OrdersTab";
import { ReceiptsTab } from "../features/purchasing/ReceiptsTab";
import { SuppliersTab } from "../features/purchasing/SuppliersTab";

const TABS = ["orders", "receipts", "invoices", "suppliers"] as const;
type TabKey = (typeof TABS)[number];

/** Purchasing: orders to suppliers, goods that arrived, supplier invoices, suppliers. */
export function PurchasingPage() {
  const { t } = useTranslation();
  const { current } = useSession();
  const [params, setParams] = useSearchParams();
  const requested = params.get("tab") as TabKey | null;
  const tab: TabKey = requested && TABS.includes(requested) ? requested : "orders";
  const businessId = current!.business.id;
  const canEdit = can(current?.role, "managePurchasing");

  return (
    <Stack spacing={3} sx={{ maxWidth: 1100 }}>
      <Typography variant="h4" component="h1" sx={{ fontWeight: 700 }}>
        {t("purchasing.title")}
      </Typography>
      {!can(current?.role, "viewPurchasing") ? (
        <Alert severity="info">{t("errors.permission_denied")}</Alert>
      ) : (
        <>
          <Tabs
            value={tab}
            onChange={(_, value: TabKey) => setParams({ tab: value }, { replace: true })}
            variant="scrollable"
            allowScrollButtonsMobile
          >
            {TABS.map((key) => (
              <Tab key={key} value={key} label={t(`purchasing.tabs.${key}`)} />
            ))}
          </Tabs>
          {tab === "orders" && <OrdersTab businessId={businessId} canEdit={canEdit} />}
          {tab === "receipts" && <ReceiptsTab businessId={businessId} canEdit={canEdit} />}
          {tab === "invoices" && <InvoicesTab businessId={businessId} canEdit={canEdit} />}
          {tab === "suppliers" && <SuppliersTab businessId={businessId} canEdit={canEdit} />}
        </>
      )}
    </Stack>
  );
}
