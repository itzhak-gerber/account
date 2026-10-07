import { useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { Period } from "./periods";

export type ReportName = "income" | "receipts" | "open_balances";

const PATHS: Record<ReportName, string> = {
  income: "income",
  receipts: "receipts",
  open_balances: "open-balances",
};

function query(period: Period | null): string {
  return period ? `?${new URLSearchParams({ date_from: period.from, date_to: period.to })}` : "";
}

export function useReport<T>(businessId: string, report: ReportName, period: Period | null) {
  return useQuery({
    queryKey: ["business", businessId, "reports", report, period?.from, period?.to],
    queryFn: () => api.get<T>(`/businesses/${businessId}/reports/${PATHS[report]}${query(period)}`),
  });
}

export function excelUrl(businessId: string, report: ReportName, period: Period | null): string {
  return `/api/v1/businesses/${businessId}/reports/${report}.xlsx${query(period)}`;
}

const FILE_TITLES: Record<ReportName, string> = {
  income: "הכנסות ומעמ",
  receipts: "תקבולים",
  open_balances: "חובות פתוחים",
};

/** The same name the server suggests, for browsers that prefer the link's own. */
export function excelFilename(report: ReportName, period: Period | null, today: string): string {
  const suffix = period ? `${period.from} עד ${period.to}` : today;
  return `${FILE_TITLES[report]} ${suffix}.xlsx`;
}
