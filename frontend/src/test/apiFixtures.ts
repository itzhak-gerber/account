// Realistic API responses for rendering every screen without a backend: used by the axe test
// (src/a11y.test.tsx) and by the in-browser accessibility check (scripts/a11y-browser.mjs).
const BUSINESS = {
  id: "b1",
  legal_name: "סטודיו אורן דיגיטל בע״מ",
  display_name: "סטודיו אורן",
  tax_id: "515123453",
  business_type: "company",
  address_street: "הרצל 10",
  address_city: "תל אביב",
  address_zip: "6100001",
  phone: "03-5551234",
  email: "office@example.com",
  default_currency: "ILS",
  has_logo: false,
};
const USER = { id: "u1", email: "owner@example.com", full_name: "אורן כהן" };
export const ME = {
  user: USER,
  memberships: [{ business: BUSINESS, role: "owner" }],
  mfa: true,
  csrf_token: "csrf",
};
const CUSTOMER = {
  id: "c1",
  name: "מאפיית השקד בע״מ",
  tax_id: "514987650",
  email: "bakery@example.com",
  phone: "03-5559876",
  address_street: "",
  address_city: "חיפה",
  address_zip: "",
  notes: "",
  is_archived: false,
};
const ITEM = {
  id: "i1",
  name: "ייעוץ עסקי (שעה)",
  description: "",
  item_type: "service",
  sku: "",
  barcode: "",
  unit_of_measure: "שעה",
  unit_price: "350.00",
  vat_type: "standard",
  is_archived: false,
};
const TYPES = [
  {
    type: "tax_invoice",
    title: "חשבונית מס",
    has_lines: true,
    has_payments: false,
    is_tax_document: true,
    shows_vat: true,
    has_due_date: true,
  },
  {
    type: "receipt",
    title: "קבלה",
    has_lines: false,
    has_payments: true,
    is_tax_document: false,
    shows_vat: false,
    has_due_date: false,
  },
];
const SUMMARY = {
  id: "d1",
  type: "tax_invoice",
  status: "issued",
  number: 1,
  issue_date: "2026-10-05",
  customer_name: CUSTOMER.name,
  total: "708.00",
  payment_status: "unpaid",
  balance_due: "708.00",
  created_at: "2026-10-05T10:00:00Z",
};
const DOCUMENT = {
  ...SUMMARY,
  title: "חשבונית מס",
  due_date: "2026-11-05",
  customer_id: "c1",
  customer: { ...CUSTOMER },
  currency: "ILS",
  prices_include_vat: false,
  vat_rate: "0.1800",
  subtotal: "600.00",
  discount_total: "0.00",
  vat_amount: "108.00",
  notes: "",
  allocation_number: null,
  amount_paid: "0.00",
  amount_credited: "0.00",
  allocations: [],
  deliveries: [],
  lines: [
    {
      position: 1,
      item_id: "i1",
      description: "תחזוקת אתר",
      quantity: "1.000",
      unit_of_measure: "",
      unit_price: "600.00",
      discount_percent: "0.00",
      vat_type: "standard",
      line_total: "600.00",
    },
  ],
  payments: [],
  related: [],
  original_delivered_at: null,
  issued_at: "2026-10-05T10:00:00Z",
};
const INCOME_TOTALS = {
  documents: 1,
  taxable: "600.00",
  zero_rated: "0.00",
  exempt: "0.00",
  net: "600.00",
  vat: "108.00",
  total: "708.00",
};
const AGING = {
  documents: 1,
  balance: "708.00",
  current: "708.00",
  d1_30: "0.00",
  d31_60: "0.00",
  d61_90: "0.00",
  d90_plus: "0.00",
};

/** The JSON body the API would return for `url` (lists default to empty). */
export function fixtureBody(url: string, me: unknown = ME): unknown {
  const path = url.replace(/^\/api\/v1/, "").split("?")[0];
  const routes: [RegExp, unknown][] = [
    [/^\/me$/, me],
    [
      /^\/me\/devices$/,
      [
        {
          id: "dev1",
          label: "Chrome · Windows",
          last_ip: "176.228.171.253",
          first_seen_at: "2026-10-01T10:00:00Z",
          last_seen_at: "2026-10-08T10:00:00Z",
          current: true,
        },
      ],
    ],
    [
      /^\/me\/notification-preferences$/,
      [
        { event: "payment_received", channels: { in_app: true, email: false } },
        { event: "new_device_login", channels: { in_app: true, email: true } },
      ],
    ],
    [/^\/me\/push$/, { public_key: "BOrdKG6EE4p7xmFX0MLjIZGDZuxxGM4ZFG2XCxPEcwbW4", devices: 1 }],
    [/\/document-types$/, TYPES],
    [/\/documents\/numbering$/, { next_numbers: { tax_invoice: 2, receipt: 1 } }],
    [/\/documents\/d1$/, DOCUMENT],
    [/\/documents$/, [SUMMARY]],
    [/\/customers$/, [CUSTOMER]],
    [/\/items$/, [ITEM]],
    [
      /\/reports\/dashboard$/,
      {
        vat_registered: true,
        month: "2026-10",
        income_net: "600.00",
        income_vat: "108.00",
        received: "0.00",
        open_balance: "708.00",
        open_documents: 1,
        overdue_balance: "0.00",
        overdue_documents: 0,
        income_by_month: [{ month: "2026-10", amount: "600.00" }],
      },
    ],
    [
      /\/reports\/income$/,
      {
        date_from: "2026-10-01",
        date_to: "2026-10-31",
        totals: INCOME_TOTALS,
        months: [{ ...INCOME_TOTALS, month: "2026-10" }],
        documents: [
          {
            ...INCOME_TOTALS,
            id: "d1",
            type: "tax_invoice",
            number: 1,
            issue_date: "2026-10-05",
            customer_name: CUSTOMER.name,
            customer_tax_id: CUSTOMER.tax_id,
          },
        ],
      },
    ],
    [
      /\/reports\/open-balances$/,
      {
        as_of: "2026-10-08",
        totals: AGING,
        customers: [{ ...AGING, customer_id: "c1", customer_name: CUSTOMER.name }],
        documents: [],
      },
    ],
    [/\/notifications\/unread-count$/, { unread: 1 }],
    [
      /\/notifications$/,
      [
        {
          id: "n1",
          event: "new_device_login",
          title: "כניסה לחשבון ממכשיר חדש",
          body: "Samsung Internet · Android",
          link: "/profile",
          read_at: null,
          created_at: "2026-10-08T19:32:00Z",
        },
      ],
    ],
    [
      /\/members$/,
      [
        {
          id: "m1",
          user_id: "u1",
          email: USER.email,
          full_name: USER.full_name,
          role: "owner",
          joined_at: "2026-10-01T10:00:00Z",
        },
      ],
    ],
    [/\/audit-log$/, []],
  ];
  const match = routes.find(([pattern]) => pattern.test(path));
  return match ? match[1] : [];
}
