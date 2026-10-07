import Card from "@mui/material/Card";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import type {
  AgingBucket,
  IncomeReport,
  IncomeTotals,
  OpenBalancesReport,
  PaymentMethod,
  ReceiptsReport,
} from "../../api/types";
import { formatDate, formatMoney } from "../../lib/money";
import { monthLabel } from "./periods";
import { ReportTable, type Column } from "./ReportTable";
import { SummaryRow } from "./SummaryRow";

const METHODS: PaymentMethod[] = [
  "cash",
  "check",
  "credit_card",
  "bank_transfer",
  "digital_wallet",
  "other",
];
const BUCKETS: AgingBucket[] = ["current", "d1_30", "d31_60", "d61_90", "d90_plus"];

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Stack spacing={1}>
      <Typography variant="h6" component="h2">
        {title}
      </Typography>
      <Card variant="outlined">{children}</Card>
    </Stack>
  );
}

function Empty({ text }: { text: string }) {
  return (
    <Card variant="outlined">
      <Typography sx={{ p: 2 }} color="text.secondary">
        {text}
      </Typography>
    </Card>
  );
}

function useDocTitle() {
  const { t } = useTranslation();
  return (type: string, number: number) => `${t(`docTypes.${type}`)} ${number}`;
}

export function IncomeView({ report }: { report: IncomeReport }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const docTitle = useDocTitle();
  const amounts = <T extends Omit<IncomeTotals, "documents">>(): Column<T>[] => [
    {
      key: "taxable",
      label: t("reports.taxable"),
      numeric: true,
      render: (r) => formatMoney(r.taxable),
    },
    {
      key: "zero",
      label: t("reports.zeroRated"),
      numeric: true,
      render: (r) => formatMoney(r.zero_rated),
    },
    {
      key: "exempt",
      label: t("reports.exempt"),
      numeric: true,
      render: (r) => formatMoney(r.exempt),
    },
    { key: "vat", label: t("reports.vat"), numeric: true, render: (r) => formatMoney(r.vat) },
    { key: "total", label: t("reports.gross"), numeric: true, render: (r) => formatMoney(r.total) },
  ];
  type Month = IncomeReport["months"][number];
  type Doc = IncomeReport["documents"][number];
  const { totals } = report;
  return (
    <Stack spacing={3}>
      <SummaryRow
        figures={[
          { label: t("reports.taxable"), value: formatMoney(totals.taxable) },
          {
            label: `${t("reports.zeroRated")} / ${t("reports.exempt")}`,
            value: formatMoney(Number(totals.zero_rated) + Number(totals.exempt)),
          },
          { label: t("reports.vat"), value: formatMoney(totals.vat) },
          {
            label: t("reports.gross"),
            value: formatMoney(totals.total),
            note: `${totals.documents} ${t("reports.count")}`,
          },
        ]}
      />
      <Section title={t("reports.byMonth")}>
        <ReportTable<Month>
          label={t("reports.byMonth")}
          rows={report.months}
          rowKey={(r) => r.month}
          totals={{ ...totals, month: "" }}
          columns={[
            {
              key: "month",
              label: t("reports.month"),
              render: (r) => (r.month ? monthLabel(r.month) : t("reports.total")),
            },
            { key: "count", label: t("reports.count"), numeric: true, render: (r) => r.documents },
            ...amounts<Month>(),
          ]}
        />
      </Section>
      {report.documents.length === 0 ? (
        <Empty text={t("reports.empty")} />
      ) : (
        <Section title={t("reports.documentsList")}>
          <ReportTable<Doc>
            label={t("reports.documentsList")}
            rows={report.documents}
            rowKey={(r) => r.id}
            onRowClick={(r) => void navigate(`/documents/${r.id}`)}
            columns={[
              {
                key: "doc",
                label: t("reports.document"),
                render: (r) => docTitle(r.type, r.number),
              },
              { key: "date", label: t("reports.date"), render: (r) => formatDate(r.issue_date) },
              {
                key: "customer",
                label: t("reports.customer"),
                render: (r) => r.customer_name || "—",
              },
              ...amounts<Doc>(),
            ]}
          />
        </Section>
      )}
    </Stack>
  );
}

export function ReceiptsView({ report }: { report: ReceiptsReport }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const docTitle = useDocTitle();
  const methods = METHODS.filter((m) => report.totals.by_method[m] !== undefined);
  const methodColumns = <
    T extends { by_method: ReceiptsReport["totals"]["by_method"] },
  >(): Column<T>[] =>
    methods.map((m) => ({
      key: m,
      label: t(`payMethods.${m}`),
      numeric: true,
      render: (r: T) => formatMoney(r.by_method[m] ?? 0),
    }));
  type Month = ReceiptsReport["months"][number];
  type Doc = ReceiptsReport["documents"][number];
  return (
    <Stack spacing={3}>
      <SummaryRow
        figures={[
          {
            label: t("reports.total"),
            value: formatMoney(report.totals.total),
            note: `${report.totals.documents} ${t("reports.count")}`,
          },
          ...methods.slice(0, 3).map((m) => ({
            label: t(`payMethods.${m}`),
            value: formatMoney(report.totals.by_method[m] ?? 0),
          })),
        ]}
      />
      <Section title={t("reports.byMonth")}>
        <ReportTable<Month>
          label={t("reports.byMonth")}
          rows={report.months}
          rowKey={(r) => r.month}
          totals={{ ...report.totals, month: "" }}
          columns={[
            {
              key: "month",
              label: t("reports.month"),
              render: (r) => (r.month ? monthLabel(r.month) : t("reports.total")),
            },
            { key: "count", label: t("reports.count"), numeric: true, render: (r) => r.documents },
            ...methodColumns<Month>(),
            {
              key: "total",
              label: t("reports.total"),
              numeric: true,
              render: (r) => formatMoney(r.total),
            },
          ]}
        />
      </Section>
      {report.documents.length === 0 ? (
        <Empty text={t("reports.empty")} />
      ) : (
        <Section title={t("reports.documentsList")}>
          <ReportTable<Doc>
            label={t("reports.documentsList")}
            rows={report.documents}
            rowKey={(r) => r.id}
            onRowClick={(r) => void navigate(`/documents/${r.id}`)}
            columns={[
              {
                key: "doc",
                label: t("reports.document"),
                render: (r) => docTitle(r.type, r.number),
              },
              { key: "date", label: t("reports.date"), render: (r) => formatDate(r.issue_date) },
              {
                key: "customer",
                label: t("reports.customer"),
                render: (r) => r.customer_name || "—",
              },
              ...methodColumns<Doc>(),
              {
                key: "total",
                label: t("reports.total"),
                numeric: true,
                render: (r) => formatMoney(r.total),
              },
            ]}
          />
        </Section>
      )}
    </Stack>
  );
}

export function OpenBalancesView({ report }: { report: OpenBalancesReport }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const docTitle = useDocTitle();
  const { totals } = report;
  const overdue = BUCKETS.slice(1).reduce((sum, b) => sum + Number(totals[b]), 0);
  type Customer = OpenBalancesReport["customers"][number];
  type Doc = OpenBalancesReport["documents"][number];
  if (report.documents.length === 0) return <Empty text={t("reports.noOpen")} />;
  return (
    <Stack spacing={3}>
      <SummaryRow
        figures={[
          {
            label: t("dashboard.openBalance"),
            value: formatMoney(totals.balance),
            note: t("dashboard.openDocuments", { count: totals.documents }),
          },
          { label: t("reports.buckets.current"), value: formatMoney(totals.current) },
          { label: t("reports.overdueTotal"), value: formatMoney(overdue) },
          { label: t("reports.buckets.d90_plus"), value: formatMoney(totals.d90_plus) },
        ]}
      />
      <Section title={t("reports.byCustomer")}>
        <ReportTable<Customer>
          label={t("reports.byCustomer")}
          rows={report.customers}
          rowKey={(r) => `${r.customer_id}-${r.customer_name}`}
          totals={{ ...totals, customer_id: null, customer_name: t("reports.total") }}
          columns={[
            {
              key: "customer",
              label: t("reports.customer"),
              render: (r) => r.customer_name || "—",
            },
            { key: "count", label: t("reports.count"), numeric: true, render: (r) => r.documents },
            ...BUCKETS.map((b) => ({
              key: b,
              label: t(`reports.buckets.${b}`),
              numeric: true,
              render: (r: Customer) => formatMoney(r[b]),
            })),
            {
              key: "balance",
              label: t("reports.balance"),
              numeric: true,
              render: (r) => formatMoney(r.balance),
            },
          ]}
        />
      </Section>
      <Section title={t("reports.documentsList")}>
        <ReportTable<Doc>
          label={t("reports.documentsList")}
          rows={report.documents}
          rowKey={(r) => r.id}
          onRowClick={(r) => void navigate(`/documents/${r.id}`)}
          columns={[
            { key: "doc", label: t("reports.document"), render: (r) => docTitle(r.type, r.number) },
            {
              key: "customer",
              label: t("reports.customer"),
              render: (r) => r.customer_name || "—",
            },
            { key: "date", label: t("reports.date"), render: (r) => formatDate(r.issue_date) },
            { key: "due", label: t("reports.dueDate"), render: (r) => formatDate(r.due_date) },
            {
              key: "total",
              label: t("reports.amount"),
              numeric: true,
              render: (r) => formatMoney(r.total),
            },
            {
              key: "paid",
              label: t("reports.paid"),
              numeric: true,
              render: (r) => formatMoney(r.paid),
            },
            {
              key: "balance",
              label: t("reports.balance"),
              numeric: true,
              render: (r) => formatMoney(r.balance),
            },
            {
              key: "days",
              label: t("reports.daysOverdue"),
              numeric: true,
              render: (r) => r.days_overdue || "—",
            },
          ]}
        />
      </Section>
    </Stack>
  );
}
