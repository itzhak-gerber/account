import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { AppNotification } from "../../api/types";

/** How often the bell checks for news (also on window focus). */
export const POLL_MS = 30_000;

const key = (businessId: string) => ["business", businessId, "notifications"] as const;

export function useUnreadCount(businessId: string | undefined) {
  return useQuery({
    queryKey: [...key(businessId ?? ""), "unread"],
    queryFn: () =>
      api.get<{ unread: number }>(`/businesses/${businessId}/notifications/unread-count`),
    enabled: Boolean(businessId),
    refetchInterval: POLL_MS,
    refetchOnWindowFocus: true,
  });
}

export function useNotifications(
  businessId: string,
  options: { unreadOnly?: boolean; limit?: number } = {},
) {
  const params = new URLSearchParams({ limit: String(options.limit ?? 30) });
  if (options.unreadOnly) params.set("unread_only", "true");
  return useQuery({
    queryKey: [...key(businessId), "list", params.toString()],
    queryFn: () => api.get<AppNotification[]>(`/businesses/${businessId}/notifications?${params}`),
    refetchInterval: POLL_MS,
  });
}

/** Mark the given notifications (or all, without ids) as read. */
export function useMarkRead(businessId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ids?: string[]) =>
      api.post<{ unread: number }>(
        `/businesses/${businessId}/notifications/read`,
        ids ? { ids } : {},
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: key(businessId) }),
  });
}

const RELATIVE = new Intl.RelativeTimeFormat("he", { numeric: "auto" });
const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["day", 86_400],
  ["hour", 3_600],
  ["minute", 60],
];

/** "לפני 5 דקות", "אתמול", or the date for anything older than a week. */
export function timeAgo(iso: string, now: number = Date.now()): string {
  const seconds = Math.round((new Date(iso).getTime() - now) / 1000);
  if (Math.abs(seconds) < 60) return "עכשיו";
  if (Math.abs(seconds) >= 7 * 86_400)
    return new Intl.DateTimeFormat("he-IL", { dateStyle: "short" }).format(new Date(iso));
  const [unit, size] = UNITS.find(([, s]) => Math.abs(seconds) >= s)!;
  return RELATIVE.format(Math.round(seconds / size), unit);
}
