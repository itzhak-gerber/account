import { useQuery } from "@tanstack/react-query";

import { apiGet } from "./client";

export interface SystemStatus {
  status: "ok" | "degraded";
  version: string;
  environment: string;
  database: "ok" | "unavailable";
}

export function useSystemStatus() {
  return useQuery({
    queryKey: ["system", "health"],
    queryFn: () => apiGet<SystemStatus>("/health"),
    refetchInterval: 30_000,
  });
}
