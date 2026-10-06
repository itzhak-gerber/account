import type { Customer, CustomerDetails, LineInput } from "../../api/types";

export function israelToday(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Jerusalem" }).format(new Date());
}

export function detailsFromCustomer(c: Customer): CustomerDetails {
  return {
    name: c.name,
    tax_id: c.tax_id,
    email: c.email || null,
    phone: c.phone,
    address_street: c.address_street,
    address_city: c.address_city,
    address_zip: c.address_zip,
  };
}

export const EMPTY_LINE: LineInput = {
  item_id: null,
  description: "",
  quantity: "1",
  unit_of_measure: "",
  unit_price: "",
  discount_percent: "0",
  vat_type: "standard",
};

/** A receipt's allocation as edited in the form (label/balance are display-only). */
export interface AllocationRow {
  invoice_id: string;
  amount: string;
  balance: string;
  label: string;
}
