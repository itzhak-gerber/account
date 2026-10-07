import NotificationsNoneOutlined from "@mui/icons-material/NotificationsNoneOutlined";
import Badge from "@mui/material/Badge";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import Popover from "@mui/material/Popover";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import type { AppNotification } from "../../api/types";
import { useMarkRead, useNotifications, useUnreadCount } from "./hooks";
import { NotificationList } from "./NotificationList";

function Inbox({ businessId, onClose }: { businessId: string; onClose: () => void }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const list = useNotifications(businessId, { limit: 8 });
  const markRead = useMarkRead(businessId);
  const open = (item: AppNotification) => {
    if (!item.read_at) markRead.mutate([item.id]);
    onClose();
    if (item.link) void navigate(item.link);
  };
  return (
    <Box sx={{ width: { xs: "calc(100vw - 32px)", sm: 400 }, maxWidth: 400 }}>
      <Stack
        direction="row"
        sx={{ alignItems: "center", justifyContent: "space-between", px: 2, py: 1 }}
      >
        <Typography variant="h6" component="h2">
          {t("notifications.title")}
        </Typography>
        <Button
          size="small"
          onClick={() => markRead.mutate(undefined)}
          disabled={markRead.isPending}
        >
          {t("notifications.markAllRead")}
        </Button>
      </Stack>
      <Divider />
      <Box sx={{ maxHeight: 420, overflowY: "auto" }}>
        {list.data && <NotificationList items={list.data} onOpen={open} dense />}
      </Box>
      <Divider />
      <Button
        fullWidth
        onClick={() => {
          onClose();
          void navigate("/notifications");
        }}
      >
        {t("notifications.viewAll")}
      </Button>
    </Box>
  );
}

export function NotificationBell({ businessId }: { businessId: string }) {
  const { t } = useTranslation();
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const unread = useUnreadCount(businessId).data?.unread ?? 0;
  return (
    <>
      <IconButton
        aria-label={t("notifications.bell", { count: unread })}
        onClick={(e) => setAnchor(e.currentTarget)}
        sx={{ me: 0.5 }}
      >
        <Badge badgeContent={unread} color="error" max={99}>
          <NotificationsNoneOutlined />
        </Badge>
      </IconButton>
      <Popover
        open={anchor !== null}
        anchorEl={anchor}
        onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
        transformOrigin={{ vertical: "top", horizontal: "left" }}
      >
        {anchor && <Inbox businessId={businessId} onClose={() => setAnchor(null)} />}
      </Popover>
    </>
  );
}
