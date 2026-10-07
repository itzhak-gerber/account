import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import Stack from "@mui/material/Stack";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link as RouterLink, useNavigate } from "react-router";

import type { AppNotification } from "../api/types";
import { useSession } from "../auth/context";
import { useMarkRead, useNotifications } from "../features/notifications/hooks";
import { NotificationList } from "../features/notifications/NotificationList";

export function NotificationsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { current } = useSession();
  const businessId = current!.business.id;
  const [filter, setFilter] = useState<"all" | "unread">("all");
  const [limit, setLimit] = useState(30);
  const list = useNotifications(businessId, { unreadOnly: filter === "unread", limit });
  const markRead = useMarkRead(businessId);
  const open = (item: AppNotification) => {
    if (!item.read_at) markRead.mutate([item.id]);
    if (item.link) void navigate(item.link);
  };

  return (
    <Stack spacing={3} sx={{ maxWidth: 760 }}>
      <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", gap: 2 }}>
        <Typography variant="h4" component="h1" sx={{ fontWeight: 700 }}>
          {t("notifications.title")}
        </Typography>
        <Button onClick={() => markRead.mutate(undefined)} disabled={markRead.isPending}>
          {t("notifications.markAllRead")}
        </Button>
      </Stack>
      <Stack
        direction="row"
        sx={{ justifyContent: "space-between", alignItems: "center", gap: 2, flexWrap: "wrap" }}
      >
        <ToggleButtonGroup
          exclusive
          size="small"
          value={filter}
          onChange={(_, value: "all" | "unread" | null) => value && setFilter(value)}
        >
          <ToggleButton value="all">{t("notifications.all")}</ToggleButton>
          <ToggleButton value="unread">{t("notifications.unreadOnly")}</ToggleButton>
        </ToggleButtonGroup>
        <Button component={RouterLink} to="/profile#notifications" size="small">
          {t("notifications.settings")}
        </Button>
      </Stack>
      <Card variant="outlined">
        {list.data && <NotificationList items={list.data} onOpen={open} />}
      </Card>
      {list.data && list.data.length >= limit && limit < 100 && (
        <Button onClick={() => setLimit(100)}>{t("notifications.more")}</Button>
      )}
    </Stack>
  );
}
