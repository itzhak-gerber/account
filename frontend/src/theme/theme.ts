import { createTheme } from "@mui/material/styles";

export const theme = createTheme({
  direction: "rtl",
  // Text and coloured controls meet WCAG AA contrast (4.5:1) on both the page background and
  // white cards (checked by scripts/a11y-browser.mjs).
  palette: {
    primary: { main: "#1e4fd8" },
    secondary: { main: "#0b7a5c" },
    warning: { main: "#b45309" },
    info: { main: "#01579b" },
    text: { secondary: "#5f6368" },
    action: { active: "rgba(0, 0, 0, 0.64)" },
    background: { default: "#f5f7fb" },
  },
  typography: {
    fontFamily: '"Heebo", "Arial", sans-serif',
  },
  shape: { borderRadius: 10 },
  components: {
    MuiButton: { defaultProps: { disableElevation: true } },
  },
});
