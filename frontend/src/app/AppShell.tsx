import AccountCircleOutlined from "@mui/icons-material/AccountCircleOutlined";
import MenuIcon from "@mui/icons-material/Menu";
import MoreHorizIcon from "@mui/icons-material/MoreHoriz";
import AppBar from "@mui/material/AppBar";
import BottomNavigation from "@mui/material/BottomNavigation";
import BottomNavigationAction from "@mui/material/BottomNavigationAction";
import Box from "@mui/material/Box";
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Divider from "@mui/material/Divider";
import Paper from "@mui/material/Paper";
import TextField from "@mui/material/TextField";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Outlet, useLocation, useNavigate } from "react-router";

import { useSession } from "../auth/context";
import { NotificationBell } from "../features/notifications/NotificationBell";
import { MfaRequiredPage } from "../pages/MfaRequiredPage";
import { NAV_ITEMS } from "./navigation";

const DRAWER_WIDTH = 240;

export function AppShell() {
  const { t } = useTranslation();
  const theme = useTheme();
  const isDesktop = useMediaQuery(theme.breakpoints.up("md"));
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const { me, current, selectBusiness, logout } = useSession();
  const [userMenu, setUserMenu] = useState<HTMLElement | null>(null);
  // Owners and admins must sign in with two-factor authentication before using the business.
  const mfaWall =
    current !== null && (current.role === "owner" || current.role === "admin") && !me.mfa;

  const go = (path: string) => {
    setMobileMenuOpen(false);
    void navigate(path);
  };

  const navList = (
    <List component="nav" aria-label={t("app.name")}>
      {NAV_ITEMS.map((item) => (
        <ListItemButton
          key={item.path}
          selected={location.pathname === item.path}
          onClick={() => go(item.path)}
          sx={{ mx: 1, borderRadius: 2 }}
        >
          <ListItemIcon sx={{ minWidth: 40 }}>{item.icon}</ListItemIcon>
          <ListItemText primary={t(item.labelKey)} />
        </ListItemButton>
      ))}
    </List>
  );

  const primaryItems = NAV_ITEMS.filter((item) => item.primary);
  const bottomValue = primaryItems.some((i) => i.path === location.pathname)
    ? location.pathname
    : "more";

  return (
    <Box sx={{ display: "flex", minHeight: "100dvh" }}>
      <AppBar
        position="fixed"
        elevation={0}
        sx={{ zIndex: (th) => th.zIndex.drawer + 1, borderBottom: 1, borderColor: "divider" }}
        color="inherit"
      >
        <Toolbar>
          {!isDesktop && (
            <IconButton
              edge="start"
              aria-label={t("app.openMenu")}
              onClick={() => setMobileMenuOpen(true)}
              sx={{ me: 1 }}
            >
              <MenuIcon />
            </IconButton>
          )}
          <Typography variant="h6" component="div" sx={{ fontWeight: 700, color: "primary.main" }}>
            {t("app.name")}
          </Typography>
          <Box sx={{ flexGrow: 1 }} />
          {me.memberships.length > 1 && current && (
            <TextField
              select
              size="small"
              label={t("app.business")}
              value={current.business.id}
              onChange={(e) => selectBusiness(e.target.value)}
              sx={{ minWidth: { xs: 120, sm: 200 }, maxWidth: 260, me: 1 }}
            >
              {me.memberships.map((m) => (
                <MenuItem key={m.business.id} value={m.business.id}>
                  {m.business.display_name}
                </MenuItem>
              ))}
            </TextField>
          )}
          {me.memberships.length === 1 && current && (
            <Typography
              noWrap
              sx={{ display: { xs: "none", sm: "block" }, me: 1, color: "text.secondary" }}
            >
              {current.business.display_name}
            </Typography>
          )}
          {current && <NotificationBell businessId={current.business.id} />}
          <IconButton
            aria-label={t("app.userMenu")}
            onClick={(e) => setUserMenu(e.currentTarget)}
            edge="end"
          >
            <AccountCircleOutlined />
          </IconButton>
          <Menu anchorEl={userMenu} open={userMenu !== null} onClose={() => setUserMenu(null)}>
            <Box sx={{ px: 2, py: 1 }}>
              <Typography sx={{ fontWeight: 500 }}>{me.user.full_name}</Typography>
              <Typography
                variant="body2"
                color="text.secondary"
                dir="ltr"
                sx={{ textAlign: "right" }}
              >
                {me.user.email}
              </Typography>
            </Box>
            <Divider />
            <MenuItem
              onClick={() => {
                setUserMenu(null);
                go("/profile");
              }}
            >
              {t("nav.profile")}
            </MenuItem>
            <MenuItem onClick={() => void logout()}>{t("nav.logout")}</MenuItem>
          </Menu>
        </Toolbar>
      </AppBar>

      {isDesktop ? (
        <Drawer
          variant="permanent"
          sx={{
            width: DRAWER_WIDTH,
            flexShrink: 0,
            "& .MuiDrawer-paper": { width: DRAWER_WIDTH, boxSizing: "border-box" },
          }}
        >
          <Toolbar />
          {navList}
        </Drawer>
      ) : (
        <Drawer
          variant="temporary"
          open={mobileMenuOpen}
          onClose={() => setMobileMenuOpen(false)}
          ModalProps={{ keepMounted: true }}
          sx={{ "& .MuiDrawer-paper": { width: DRAWER_WIDTH } }}
        >
          <Toolbar />
          {navList}
        </Drawer>
      )}

      <Box
        component="main"
        sx={{ flexGrow: 1, minWidth: 0, p: { xs: 2, md: 4 }, pb: { xs: 10, md: 4 } }}
      >
        <Toolbar />
        {mfaWall && location.pathname !== "/profile" ? <MfaRequiredPage /> : <Outlet />}
      </Box>

      {!isDesktop && (
        <Paper
          elevation={3}
          sx={{ position: "fixed", insetInline: 0, bottom: 0, pb: "env(safe-area-inset-bottom)" }}
        >
          <BottomNavigation
            showLabels
            value={bottomValue}
            onChange={(_, value: string) =>
              value === "more" ? setMobileMenuOpen(true) : go(value)
            }
          >
            {primaryItems.map((item) => (
              <BottomNavigationAction
                key={item.path}
                value={item.path}
                label={t(item.labelKey)}
                icon={item.icon}
              />
            ))}
            <BottomNavigationAction value="more" label={t("nav.more")} icon={<MoreHorizIcon />} />
          </BottomNavigation>
        </Paper>
      )}
    </Box>
  );
}
