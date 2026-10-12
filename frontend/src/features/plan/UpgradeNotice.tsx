import LockOutlined from "@mui/icons-material/LockOutlined";
import Alert from "@mui/material/Alert";
import AlertTitle from "@mui/material/AlertTitle";
import Button from "@mui/material/Button";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { ModuleName } from "../../api/types";
import { UpgradeDialog } from "./UpgradeDialog";

/** Shown where a module that is not in the plan would be: what it does, and how to get it. */
export function UpgradeNotice({ module }: { module: ModuleName }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const name = t(`plan.moduleNames.${module}`);
  return (
    <>
      <Alert
        severity="info"
        icon={<LockOutlined />}
        action={
          <Button color="inherit" size="small" onClick={() => setOpen(true)}>
            {t("plan.details")}
          </Button>
        }
      >
        <AlertTitle>{t("plan.upgradeTitle", { module: name })}</AlertTitle>
        {t(`plan.moduleHelp.${module}`)}
      </Alert>
      {open && <UpgradeDialog module={module} onClose={() => setOpen(false)} />}
    </>
  );
}

/** A small button in place of a locked action (e.g. scanning a supplier invoice). */
export function UpgradeButton({ module, label }: { module: ModuleName; label: string }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button
        variant="outlined"
        startIcon={<LockOutlined />}
        onClick={() => setOpen(true)}
        aria-label={`${label} – ${t("nav.upgrade")}`}
      >
        {label}
      </Button>
      {open && <UpgradeDialog module={module} onClose={() => setOpen(false)} />}
    </>
  );
}
