import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import type { ReactNode } from "react";

export interface Figure {
  label: string;
  value: string;
  note?: ReactNode;
}

/** A row of headline numbers (stat tiles), wrapping on narrow screens. */
export function SummaryRow({ figures }: { figures: Figure[] }) {
  return (
    <Box
      sx={{
        display: "grid",
        gap: 2,
        gridTemplateColumns: {
          xs: "repeat(2, minmax(0, 1fr))",
          md: `repeat(${figures.length}, minmax(0, 1fr))`,
        },
      }}
    >
      {figures.map((f) => (
        <Card key={f.label} variant="outlined">
          <CardContent sx={{ "&:last-child": { pb: 2 } }}>
            <Typography variant="body2" color="text.secondary">
              {f.label}
            </Typography>
            <Typography variant="h5" component="p" sx={{ fontWeight: 600, mt: 0.5 }}>
              {f.value}
            </Typography>
            {f.note && (
              <Typography variant="body2" color="text.secondary" component="div" sx={{ mt: 0.5 }}>
                {f.note}
              </Typography>
            )}
          </CardContent>
        </Card>
      ))}
    </Box>
  );
}
