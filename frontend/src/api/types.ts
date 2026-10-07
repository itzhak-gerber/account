export type Role = "owner" | "admin" | "accountant" | "member" | "viewer";
export type BusinessType = "exempt_dealer" | "licensed_dealer" | "company" | "nonprofit";

export interface User {
  id: string;
  email: string;
  full_name: string;
}

export interface Business {
  id: string;
  legal_name: string;
  display_name: string;
  tax_id: string;
  business_type: BusinessType;
  address_street: string;
  address_city: string;
  address_zip: string;
  phone: string;
  email: string;
  default_currency: string;
  has_logo: boolean;
}

export interface Membership {
  business: Business;
  role: Role;
}

export interface Me {
  user: User;
  memberships: Membership[];
  mfa: boolean;
  csrf_token: string | null;
}

export interface Member {
  id: string;
  user_id: string;
  email: string;
  full_name: string;
  role: Role;
  joined_at: string;
}

export interface Invitation {
  id: string;
  email: string;
  role: Role;
  expires_at: string;
  created_at: string;
}

export interface InvitationPreview {
  business_name: string;
  invited_by_name: string;
  email: string;
  role: Role;
  expires_at: string;
  status: "pending" | "expired" | "accepted" | "revoked";
}

export interface AuditEntry {
  id: string;
  actor_email: string | null;
  actor_channel: "web" | "api" | "mcp" | "system";
  action: string;
  entity_type: string;
  changes: Record<string, unknown>;
  ip: string | null;
  created_at: string;
}

export type BusinessInput = Omit<Business, "id" | "default_currency" | "email" | "has_logo"> & {
  email: string | null;
};

export type VatType = "standard" | "exempt" | "zero";
export type ItemType = "product" | "service";
export type DocumentType =
  "quote" | "proforma_invoice" | "tax_invoice" | "receipt" | "tax_invoice_receipt" | "credit_note";
export type DocumentStatus = "draft" | "issued";
export type PaymentMethod =
  "cash" | "check" | "credit_card" | "bank_transfer" | "digital_wallet" | "other";

export interface Customer {
  id: string;
  name: string;
  tax_id: string;
  email: string;
  phone: string;
  address_street: string;
  address_city: string;
  address_zip: string;
  notes: string;
  is_archived: boolean;
}

export type CustomerInput = Omit<Customer, "id" | "is_archived" | "email"> & {
  email: string | null;
};

export interface Item {
  id: string;
  name: string;
  description: string;
  item_type: ItemType;
  sku: string;
  barcode: string;
  unit_of_measure: string;
  unit_price: string;
  vat_type: VatType;
  is_archived: boolean;
}

export type ItemInput = Omit<Item, "id" | "is_archived">;

export interface DocumentTypeInfo {
  type: DocumentType;
  title: string;
  has_lines: boolean;
  has_payments: boolean;
  is_tax_document: boolean;
  shows_vat: boolean;
  has_due_date: boolean;
}

export interface CustomerDetails {
  name: string;
  tax_id: string;
  email: string | null;
  phone: string;
  address_street: string;
  address_city: string;
  address_zip: string;
}

export interface LineInput {
  item_id: string | null;
  description: string;
  quantity: string;
  unit_of_measure: string;
  unit_price: string;
  discount_percent: string;
  vat_type: VatType;
}

export interface PaymentDetails {
  bank?: string;
  branch?: string;
  account?: string;
  check_number?: string;
  card_last4?: string;
  installments?: number | null;
  reference?: string;
}

export interface PaymentInput {
  method: PaymentMethod;
  amount: string;
  payment_date: string;
  details: PaymentDetails;
}

/** superseded: a proforma replaced by the tax invoice issued from it. */
export type PaymentStatus = "unpaid" | "partial" | "paid" | "superseded";

export interface AllocationInput {
  invoice_id: string;
  amount: string;
}

export interface Allocation {
  invoice_id: string;
  invoice_type: DocumentType;
  invoice_number: number | null;
  invoice_date: string;
  invoice_total: string;
  amount: string;
  balance_due: string;
}

export interface RelatedDocument {
  id: string;
  type: DocumentType;
  number: number | null;
  status: DocumentStatus;
  relation: "converted_from" | "credits" | "pays";
  amount: string | null;
  direction: "outgoing" | "incoming";
}

export interface InvoiceDocument {
  id: string;
  type: DocumentType;
  title: string;
  status: DocumentStatus;
  number: number | null;
  issue_date: string;
  due_date: string | null;
  customer_id: string | null;
  customer: CustomerDetails;
  currency: string;
  prices_include_vat: boolean;
  vat_rate: string;
  subtotal: string;
  discount_total: string;
  vat_amount: string;
  total: string;
  notes: string;
  allocation_number: string | null;
  payment_status: PaymentStatus | null;
  amount_paid: string;
  amount_credited: string;
  balance_due: string | null;
  allocations: Allocation[];
  deliveries: Delivery[];
  lines: (LineInput & { id: string; line_total: string })[];
  payments: (PaymentInput & { id: string })[];
  related: RelatedDocument[];
  original_delivered_at: string | null;
  issued_at: string | null;
  created_at: string;
}

export interface DocumentSummary {
  id: string;
  type: DocumentType;
  status: DocumentStatus;
  number: number | null;
  issue_date: string;
  customer_name: string;
  total: string;
  payment_status: PaymentStatus | null;
  balance_due: string | null;
  created_at: string;
}

export interface Delivery {
  id: string;
  recipients: string[];
  subject: string;
  variant: "original" | "copy";
  status: "queued" | "sent" | "failed";
  error: string | null;
  sent_at: string | null;
  created_at: string;
}

export interface EmailDefaults {
  to: string[];
  subject: string;
  message: string;
}

// --- reports ------------------------------------------------------------------------

export interface IncomeTotals {
  documents: number;
  taxable: string;
  zero_rated: string;
  exempt: string;
  net: string;
  vat: string;
  total: string;
}

export interface IncomeReport {
  date_from: string;
  date_to: string;
  totals: IncomeTotals;
  months: (IncomeTotals & { month: string })[];
  documents: (Omit<IncomeTotals, "documents"> & {
    id: string;
    type: DocumentType;
    number: number;
    issue_date: string;
    customer_name: string;
    customer_tax_id: string;
  })[];
}

export interface ReceiptsTotals {
  documents: number;
  by_method: Partial<Record<PaymentMethod, string>>;
  total: string;
}

export interface ReceiptsReport {
  date_from: string;
  date_to: string;
  totals: ReceiptsTotals;
  months: (ReceiptsTotals & { month: string })[];
  documents: {
    id: string;
    type: DocumentType;
    number: number;
    issue_date: string;
    customer_name: string;
    by_method: Partial<Record<PaymentMethod, string>>;
    total: string;
  }[];
}

export type AgingBucket = "current" | "d1_30" | "d31_60" | "d61_90" | "d90_plus";

export type AgingTotals = { documents: number; balance: string } & Record<AgingBucket, string>;

export interface OpenBalancesReport {
  as_of: string;
  totals: AgingTotals;
  customers: (AgingTotals & { customer_id: string | null; customer_name: string })[];
  documents: {
    id: string;
    type: DocumentType;
    number: number;
    issue_date: string;
    due_date: string;
    customer_id: string | null;
    customer_name: string;
    total: string;
    paid: string;
    balance: string;
    days_overdue: number;
    bucket: AgingBucket;
  }[];
}

export interface Dashboard {
  vat_registered: boolean;
  month: string;
  income_net: string;
  income_vat: string;
  received: string;
  open_balance: string;
  open_documents: number;
  overdue_balance: string;
  overdue_documents: number;
  income_by_month: { month: string; amount: string }[];
}
