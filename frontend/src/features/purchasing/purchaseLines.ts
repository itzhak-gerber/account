export interface PurchaseLine {
  item_id: string | null;
  description: string;
  quantity: string;
  unit_cost: string;
  order_line_id?: string | null;
}

export function lineOk(line: PurchaseLine, productsOnly: boolean): boolean {
  return (
    (productsOnly ? Boolean(line.item_id) : line.description.trim() !== "") &&
    Number(line.quantity) > 0 &&
    line.unit_cost !== ""
  );
}

export function linesTotal(lines: PurchaseLine[]): number {
  return lines.reduce((sum, l) => sum + (Number(l.quantity) || 0) * (Number(l.unit_cost) || 0), 0);
}
