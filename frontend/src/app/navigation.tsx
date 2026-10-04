import AssessmentOutlined from "@mui/icons-material/AssessmentOutlined";
import Inventory2Outlined from "@mui/icons-material/Inventory2Outlined";
import PeopleOutlined from "@mui/icons-material/PeopleOutlined";
import ReceiptLongOutlined from "@mui/icons-material/ReceiptLongOutlined";
import SettingsOutlined from "@mui/icons-material/SettingsOutlined";
import SpaceDashboardOutlined from "@mui/icons-material/SpaceDashboardOutlined";
import type { ReactElement } from "react";

export interface NavItem {
  path: string;
  labelKey: string;
  icon: ReactElement;
  /** Shown in the mobile bottom bar (the rest live under "more"). */
  primary: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { path: "/", labelKey: "nav.dashboard", icon: <SpaceDashboardOutlined />, primary: true },
  { path: "/documents", labelKey: "nav.documents", icon: <ReceiptLongOutlined />, primary: true },
  { path: "/customers", labelKey: "nav.customers", icon: <PeopleOutlined />, primary: true },
  { path: "/items", labelKey: "nav.items", icon: <Inventory2Outlined />, primary: false },
  { path: "/reports", labelKey: "nav.reports", icon: <AssessmentOutlined />, primary: false },
  { path: "/settings", labelKey: "nav.settings", icon: <SettingsOutlined />, primary: false },
];
