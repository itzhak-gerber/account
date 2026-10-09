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
  track_inventory: false,
  min_stock: null,
  components: [],
};
const PRODUCT = {
  ...ITEM,
  id: "i2",
  name: "מקלדת אלחוטית",
  item_type: "product",
  sku: "KB-100",
  unit_of_measure: "יחידה",
  unit_price: "120.00",
  track_inventory: true,
  min_stock: "5.000",
};
const KIT = {
  ...ITEM,
  id: "i3",
  name: "ערכת עבודה מהבית",
  item_type: "kit",
  sku: "KIT-1",
  unit_of_measure: "יחידה",
  unit_price: "450.00",
  components: [{ item_id: "i2", quantity: "1.000" }],
};
const STOCK = {
  items: [
    { item: PRODUCT, quantity: "3.000", average_cost: "80.0000", value: "240.00", low: true },
  ],
  kits: [{ item: KIT, available: "3" }],
  total_value: "240.00",
};
const MOVEMENTS = [
  {
    id: "m1",
    kind: "adjustment",
    quantity: "10.000",
    unit_cost: "80.0000",
    balance_after: "10.000",
    document_id: null,
    kit_item_id: null,
    goods_receipt_id: null,
    reason: "ספירת פתיחה",
    created_at: "2026-10-01T09:00:00Z",
  },
];
const SUPPLIER = {
  id: "s1",
  name: "סיטונאות הצפון בע״מ",
  tax_id: "515555555",
  contact_name: "יוסי לוי",
  email: "orders@north.example",
  phone: "04-1234567",
  address_street: "",
  address_city: "חיפה",
  address_zip: "",
  notes: "",
  is_archived: false,
};
const SUPPLIER_REF = { id: "s1", name: SUPPLIER.name };
const ORDER = {
  id: "po1",
  number: 1,
  supplier: SUPPLIER_REF,
  status: "partial",
  order_date: "2026-10-01",
  expected_date: "2026-10-10",
  notes: "",
  total: "1000.00",
  lines: [
    {
      id: "pol1",
      item_id: "i2",
      description: "מקלדת אלחוטית",
      quantity: "30.000",
      unit_cost: "30.0000",
      received_quantity: "10.000",
      total: "900.00",
    },
    {
      id: "pol2",
      item_id: null,
      description: "הובלה",
      quantity: "1.000",
      unit_cost: "100.0000",
      received_quantity: "0.000",
      total: "100.00",
    },
  ],
  created_at: "2026-10-01T09:00:00Z",
};
const GOODS_RECEIPT = {
  id: "gr1",
  number: 1,
  supplier: SUPPLIER_REF,
  purchase_order_id: "po1",
  receipt_date: "2026-10-05",
  supplier_reference: "5521",
  notes: "",
  total: "300.00",
  lines: [
    {
      id: "grl1",
      item_id: "i2",
      order_line_id: "pol1",
      description: "מקלדת אלחוטית",
      quantity: "10.000",
      unit_cost: "30.0000",
      total: "300.00",
    },
  ],
  created_at: "2026-10-05T09:00:00Z",
};
const SUPPLIER_INVOICES = [
  {
    id: "si1",
    supplier: SUPPLIER_REF,
    purchase_order_id: "po1",
    invoice_number: "A-1001",
    invoice_date: "2026-10-05",
    due_date: "2026-10-08",
    net_amount: "300.00",
    vat_amount: "54.00",
    total: "354.00",
    paid_date: null,
    notes: "",
    created_at: "2026-10-05T09:00:00Z",
  },
  {
    id: "si2",
    supplier: SUPPLIER_REF,
    purchase_order_id: null,
    invoice_number: "A-0990",
    invoice_date: "2026-09-20",
    due_date: null,
    net_amount: "100.00",
    vat_amount: "18.00",
    total: "118.00",
    paid_date: "2026-09-30",
    notes: "",
    created_at: "2026-09-20T09:00:00Z",
  },
];
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
  delivery_status: null,
  created_at: "2026-10-05T10:00:00Z",
};
const DELIVERY_NOTES = [3, 4].map((number) => ({
  id: `dn${number}`,
  type: "delivery_note",
  status: "issued",
  number,
  issue_date: `2026-10-0${number}`,
  customer_name: CUSTOMER.name,
  total: "0.00",
  payment_status: null,
  balance_due: null,
  delivery_status: "open",
  created_at: `2026-10-0${number}T10:00:00Z`,
}));
const DOCUMENT = {
  ...SUMMARY,
  title: "חשבונית מס",
  due_date: "2026-11-05",
  customer_id: "c1",
  customer: { ...CUSTOMER },
  currency: "ILS",
  prices_include_vat: false,
  returns_stock: true,
  vat_rate: "0.1800",
  subtotal: "600.00",
  discount_total: "0.00",
  vat_amount: "108.00",
  notes: "",
  allocation_number: null,
  allocation_status: null,
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
  if (url.includes("uninvoiced=true")) return DELIVERY_NOTES;
  if (url.endsWith("/ita"))
    return {
      enabled: true,
      environment: "sandbox",
      connected: true,
      connected_at: "2026-10-01T10:00:00Z",
      expires_at: "2026-12-30T10:00:00Z",
      threshold: "5000",
      redirect_uri: "https://invoice.example/api/v1/ita/callback",
    };
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
    [
      /\/exports$/,
      [
        {
          id: "e1",
          status: "ready",
          created_at: "2026-10-09T08:00:00Z",
          finished_at: "2026-10-09T08:01:00Z",
          expires_at: "2099-10-16T08:01:00Z",
          size: 2_400_000,
          documents: 12,
          date_from: "2026-01-01",
          date_to: "2026-10-09",
          downloadable: true,
        },
      ],
    ],
    [/\/document-types$/, TYPES],
    [/\/documents\/numbering$/, { next_numbers: { tax_invoice: 2, receipt: 1 } }],
    [/\/documents\/d1$/, DOCUMENT],
    [/\/documents$/, [SUMMARY, ...DELIVERY_NOTES]],
    [/\/customers$/, [CUSTOMER]],
    [/\/items$/, [ITEM, PRODUCT, KIT]],
    [/\/inventory\/[^/]+\/movements$/, MOVEMENTS],
    [/\/inventory$/, STOCK],
    [/\/suppliers$/, [SUPPLIER]],
    [/\/purchase-orders$/, [ORDER]],
    [/\/goods-receipts$/, [GOODS_RECEIPT]],
    [/\/supplier-invoices$/, SUPPLIER_INVOICES],
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
