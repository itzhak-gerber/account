import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link as RouterLink } from "react-router";

import { api } from "../api/client";
import type { Item, Stock, StockItem } from "../api/types";
import { useSession } from "../auth/context";
import { can } from "../auth/permissions";
import { AdjustDialog } from "../features/inventory/AdjustDialog";
import { MovementsDialog } from "../features/inventory/MovementsDialog";
import { formatMoney } from "../lib/money";

const qty = (value: string | number) => Number(value).toLocaleString("he-IL");
// Read by screen readers only (a column heading without visible text).
const SR_ONLY = {
  position: "absolute",
  width: 1,
  height: 1,
  overflow: "hidden",
  clipPath: "inset(50%)",
  whiteSpace: "nowrap",
} as const;

export function InventoryPage() {
  const { t } = useTranslation();
  const { current } = useSession();
  const businessId = current!.business.id;
  const canAdjust = can(current?.role, "manageCatalog");
  const stock = useQuery({
    queryKey: ["business", businessId, "inventory"],
    queryFn: () => api.get<Stock>(`/businesses/${businessId}/inventory`),
  });
  const [adjusting, setAdjusting] = useState<StockItem | null>(null);
  const [history, setHistory] = useState<Item | null>(null);
  const low = stock.data?.items.filter((r) => r.low) ?? [];

  return (
    <Stack spacing={3} sx={{ maxWidth: 1100 }}>
      <Typography variant="h4" component="h1" sx={{ fontWeight: 700 }}>
        {t("inventory.title")}
      </Typography>
      {low.length > 0 && (
        <Alert severity="warning">
          {t("inventory.lowAlert", { names: low.map((r) => r.item.name).join(", ") })}
        </Alert>
      )}
      {stock.data && stock.data.items.length === 0 && stock.data.kits.length === 0 && (
        <Alert severity="info">
          {t("inventory.empty")}{" "}
          <Button component={RouterLink} to="/items" size="small">
            {t("inventory.toItems")}
          </Button>
        </Alert>
      )}

      {stock.data && stock.data.items.length > 0 && (
        <Card variant="outlined">
          <CardContent>
            <Stack
              direction="row"
              sx={{ justifyContent: "space-between", alignItems: "baseline", mb: 1 }}
            >
              <Typography variant="h6" component="h2">
                {t("inventory.products")}
              </Typography>
              <Typography>
                {t("inventory.totalValue")}: <strong>{formatMoney(stock.data.total_value)}</strong>
              </Typography>
            </Stack>
            <TableContainer tabIndex={0} role="region" aria-label={t("inventory.products")}>
              <Table size="small" aria-label={t("inventory.products")}>
                <TableHead>
                  <TableRow>
                    <TableCell>{t("inventory.item")}</TableCell>
                    <TableCell align="left">{t("inventory.quantity")}</TableCell>
                    <TableCell align="left">{t("inventory.minimum")}</TableCell>
                    <TableCell align="left">{t("inventory.averageCost")}</TableCell>
                    <TableCell align="left">{t("inventory.value")}</TableCell>
                    <TableCell>
                      <Box component="span" sx={SR_ONLY}>
                        {t("inventory.actions")}
                      </Box>
                    </TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {stock.data.items.map((row) => (
                    <TableRow key={row.item.id}>
                      <TableCell>
                        {row.item.name}
                        {row.item.sku && (
                          <Typography variant="body2" color="text.secondary" component="span">
                            {" "}
                            · {row.item.sku}
                          </Typography>
                        )}
                        {row.low && (
                          <Chip
                            size="small"
                            color="warning"
                            variant="outlined"
                            label={t("inventory.low")}
                            sx={{ ms: 1 }}
                          />
                        )}
                      </TableCell>
                      <TableCell
                        align="left"
                        sx={{ color: Number(row.quantity) < 0 ? "error.main" : undefined }}
                      >
                        {qty(row.quantity)}
                      </TableCell>
                      <TableCell align="left">
                        {row.item.min_stock ? qty(row.item.min_stock) : "—"}
                      </TableCell>
                      <TableCell align="left">{formatMoney(row.average_cost)}</TableCell>
                      <TableCell align="left">{formatMoney(row.value)}</TableCell>
                      <TableCell sx={{ whiteSpace: "nowrap" }}>
                        {canAdjust && (
                          <Button size="small" onClick={() => setAdjusting(row)}>
                            {t("inventory.adjust")}
                          </Button>
                        )}
                        <Button size="small" onClick={() => setHistory(row.item)}>
                          {t("inventory.history")}
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        </Card>
      )}

      {stock.data && stock.data.kits.length > 0 && (
        <Card variant="outlined">
          <CardContent>
            <Typography variant="h6" component="h2" gutterBottom>
              {t("inventory.kits")}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              {t("inventory.kitsHelp")}
            </Typography>
            <TableContainer tabIndex={0} role="region" aria-label={t("inventory.kits")}>
              <Table size="small" aria-label={t("inventory.kits")}>
                <TableHead>
                  <TableRow>
                    <TableCell>{t("inventory.kit")}</TableCell>
                    <TableCell align="left">{t("inventory.available")}</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {stock.data.kits.map((k) => (
                    <TableRow key={k.item.id}>
                      <TableCell>{k.item.name}</TableCell>
                      <TableCell align="left">
                        {k.available === null ? "—" : qty(k.available)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        </Card>
      )}

      {adjusting && (
        <AdjustDialog businessId={businessId} row={adjusting} onClose={() => setAdjusting(null)} />
      )}
      {history && (
        <MovementsDialog businessId={businessId} item={history} onClose={() => setHistory(null)} />
      )}
    </Stack>
  );
}
