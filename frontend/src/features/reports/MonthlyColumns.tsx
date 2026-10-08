import Box from "@mui/material/Box";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import { formatMoney } from "../../lib/money";
import { monthLabel } from "./periods";

const PLOT_HEIGHT = 160;
const compact = new Intl.NumberFormat("he-IL", { notation: "compact", maximumFractionDigits: 1 });

/** A clean axis maximum: 1, 2, 2.5 or 5 times a power of ten. */
function niceMax(value: number): number {
  if (value <= 0) return 1;
  const power = 10 ** Math.floor(Math.log10(value));
  const step = [1, 2, 2.5, 5, 10].find((m) => m * power >= value) ?? 10;
  return step * power;
}

/**
 * One series of monthly amounts as columns, oldest on the left (like the Excel export).
 * Hover or focus a month for its exact amount; the current month carries a label. Screen
 * readers get a named group with one "month: amount" image per column.
 */
export function MonthlyColumns({
  data,
  title,
}: {
  data: { month: string; amount: string }[];
  title: string;
}) {
  const values = data.map((d) => Math.max(Number(d.amount), 0));
  const max = niceMax(Math.max(...values, 0));
  const ticks = [max, max / 2, 0];
  const last = data.length - 1;

  return (
    <Box sx={{ position: "relative" }}>
      <Box dir="ltr" sx={{ display: "flex", gap: 1 }} role="group" aria-label={title}>
        <Box
          aria-hidden
          sx={{
            height: PLOT_HEIGHT,
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
            alignItems: "flex-end",
            minWidth: 40,
          }}
        >
          {ticks.map((tick) => (
            <Typography
              key={tick}
              variant="caption"
              color="text.secondary"
              sx={{ lineHeight: 0, fontVariantNumeric: "tabular-nums" }}
            >
              {compact.format(tick)}
            </Typography>
          ))}
        </Box>
        <Box sx={{ flex: 1, minWidth: 0, overflow: "hidden" }}>
          <Box
            sx={{
              position: "relative",
              height: PLOT_HEIGHT,
              display: "flex",
              alignItems: "flex-end",
              borderBottom: 1,
              borderColor: "divider",
            }}
          >
            {ticks.slice(0, -1).map((tick) => (
              <Box
                key={tick}
                sx={{
                  position: "absolute",
                  insetInline: 0,
                  bottom: `${(tick / max) * 100}%`,
                  borderTop: 1,
                  borderColor: "grey.200",
                }}
              />
            ))}
            {data.map((d, i) => (
              <Tooltip
                key={d.month}
                title={`${monthLabel(d.month)}: ${formatMoney(d.amount)}`}
                placement="top"
              >
                <Box
                  tabIndex={0}
                  role="img"
                  aria-label={`${monthLabel(d.month)}: ${formatMoney(d.amount)}`}
                  sx={{
                    position: "relative",
                    flex: 1,
                    minWidth: 0,
                    height: "100%",
                    display: "flex",
                    alignItems: "flex-end",
                    justifyContent: "center",
                    cursor: "default",
                    outline: "none",
                    "&:hover > .column, &:focus-visible > .column": { opacity: 0.8 },
                    "&:focus-visible": { bgcolor: "action.hover" },
                  }}
                >
                  {i === last && values[i] > 0 && (
                    <Typography
                      aria-hidden
                      variant="caption"
                      sx={{
                        position: "absolute",
                        bottom: `calc(${(values[i] / max) * 100}% + 4px)`,
                        whiteSpace: "nowrap",
                        fontWeight: 600,
                      }}
                    >
                      {compact.format(values[i])}
                    </Typography>
                  )}
                  <Box
                    className="column"
                    sx={{
                      width: "60%",
                      maxWidth: 24,
                      height: `${(values[i] / max) * 100}%`,
                      minHeight: values[i] > 0 ? 2 : 0,
                      bgcolor: "primary.main",
                      borderRadius: "4px 4px 0 0",
                    }}
                  />
                </Box>
              </Tooltip>
            ))}
          </Box>
          <Box aria-hidden sx={{ display: "flex", mt: 0.5 }}>
            {data.map((d, i) => (
              <Typography
                key={d.month}
                variant="caption"
                color="text.secondary"
                sx={{
                  flex: 1,
                  minWidth: 0,
                  textAlign: "center",
                  whiteSpace: "nowrap",
                  // On phones, label every other month (always the latest).
                  visibility: { xs: (last - i) % 2 === 0 ? "visible" : "hidden", sm: "visible" },
                }}
              >
                {monthLabel(d.month, "short")}
              </Typography>
            ))}
          </Box>
        </Box>
      </Box>
    </Box>
  );
}
