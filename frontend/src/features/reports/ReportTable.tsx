import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import type { ReactNode } from "react";

export interface Column<T> {
  key: string;
  label: string;
  numeric?: boolean;
  render: (row: T) => ReactNode;
}

/** A compact table that scrolls sideways inside its card on narrow screens. */
export function ReportTable<T>({
  columns,
  rows,
  rowKey,
  totals,
  onRowClick,
  label,
}: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  totals?: T;
  onRowClick?: (row: T) => void;
  label: string;
}) {
  const cell = (column: Column<T>, row: T, bold = false) => (
    <TableCell
      key={column.key}
      align={column.numeric ? "right" : "left"}
      sx={{
        whiteSpace: "nowrap",
        fontWeight: bold ? 700 : undefined,
        fontVariantNumeric: column.numeric ? "tabular-nums" : undefined,
      }}
    >
      {column.render(row)}
    </TableCell>
  );
  return (
    // Wide tables scroll sideways on phones; focusable so the keyboard can scroll them too.
    <TableContainer tabIndex={0} role="region" aria-label={label}>
      <Table size="small" aria-label={label}>
        <TableHead>
          <TableRow>
            {columns.map((c) => (
              <TableCell
                key={c.key}
                align={c.numeric ? "right" : "left"}
                sx={{ whiteSpace: "nowrap", fontWeight: 600, color: "text.secondary" }}
              >
                {c.label}
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row) => (
            <TableRow
              key={rowKey(row)}
              hover={Boolean(onRowClick)}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              sx={onRowClick ? { cursor: "pointer" } : undefined}
            >
              {columns.map((c) => cell(c, row))}
            </TableRow>
          ))}
          {totals && (
            <TableRow sx={{ "& td": { borderTop: 2, borderColor: "divider", borderBottom: 0 } }}>
              {columns.map((c) => cell(c, totals, true))}
            </TableRow>
          )}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
