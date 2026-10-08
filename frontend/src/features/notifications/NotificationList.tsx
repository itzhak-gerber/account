import DevicesOutlined from "@mui/icons-material/DevicesOutlined";
import ErrorOutlineRounded from "@mui/icons-material/ErrorOutlineRounded";
import EventBusyOutlined from "@mui/icons-material/EventBusyOutlined";
import PaymentsOutlined from "@mui/icons-material/PaymentsOutlined";
import PersonAddAltOutlined from "@mui/icons-material/PersonAddAltOutlined";
import ReceiptLongOutlined from "@mui/icons-material/ReceiptLongOutlined";
import SummarizeOutlined from "@mui/icons-material/SummarizeOutlined";
import Box from "@mui/material/Box";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Typography from "@mui/material/Typography";
import type { ReactElement } from "react";
import { useTranslation } from "react-i18next";

import type { AppNotification, NotificationEvent } from "../../api/types";
import { timeAgo } from "./hooks";

const ICONS: Record<NotificationEvent, ReactElement> = {
  payment_received: <PaymentsOutlined color="success" />,
  document_issued: <ReceiptLongOutlined color="primary" />,
  invoice_overdue: <EventBusyOutlined color="warning" />,
  email_failed: <ErrorOutlineRounded color="error" />,
  member_joined: <PersonAddAltOutlined color="primary" />,
  daily_summary: <SummarizeOutlined color="primary" />,
  new_device_login: <DevicesOutlined color="warning" />,
};

export function NotificationList({
  items,
  onOpen,
  dense = false,
}: {
  items: AppNotification[];
  onOpen: (item: AppNotification) => void;
  dense?: boolean;
}) {
  const { t } = useTranslation();
  if (items.length === 0)
    return (
      <Typography color="text.secondary" sx={{ p: 2 }}>
        {t("notifications.empty")}
      </Typography>
    );
  return (
    <List disablePadding aria-label={t("notifications.title")}>
      {items.map((n) => {
        const unread = n.read_at === null;
        return (
          <ListItem key={n.id} disablePadding>
            <ListItemButton
              divider
              dense={dense}
              onClick={() => onOpen(n)}
              sx={{ alignItems: "flex-start", bgcolor: unread ? "action.hover" : undefined }}
            >
              <ListItemIcon sx={{ minWidth: 40, mt: 0.5 }}>{ICONS[n.event]}</ListItemIcon>
              <ListItemText
                primary={
                  <Typography component="span" sx={{ fontWeight: unread ? 700 : 400 }}>
                    {n.title}
                  </Typography>
                }
                secondary={
                  <>
                    <Box component="span" sx={{ display: "block" }}>
                      {n.body}
                    </Box>
                    <Box component="span" sx={{ display: "block", mt: 0.25 }}>
                      {timeAgo(n.created_at)}
                    </Box>
                  </>
                }
              />
              {unread && (
                <Box
                  role="img"
                  aria-label={t("notifications.unread")}
                  sx={{
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                    bgcolor: "primary.main",
                    mt: 1.25,
                    ms: 1,
                  }}
                />
              )}
            </ListItemButton>
          </ListItem>
        );
      })}
    </List>
  );
}
