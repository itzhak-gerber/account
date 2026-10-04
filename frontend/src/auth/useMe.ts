import { useQuery } from "@tanstack/react-query";

import { ApiError, api, setCsrfToken } from "../api/client";
import type { Me } from "../api/types";

export function useMeQuery() {
  return useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        const me = await api.get<Me>("/me");
        setCsrfToken(me.csrf_token);
        return me;
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
    staleTime: 60_000,
  });
}
