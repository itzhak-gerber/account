import { createTheme } from "@mui/material/styles";

export const theme = createTheme({
  direction: "rtl",
  palette: {
    primary: { main: "#1e4fd8" },
    secondary: { main: "#0f9d76" },
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
