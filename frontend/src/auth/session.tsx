import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo, useState, type ReactNode } from "react";

import { api, setCsrfToken } from "../api/client";
import type { Me } from "../api/types";
import { SessionContext } from "./context";

const STORAGE_KEY = "currentBusinessId";

function readStoredBusiness(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function SessionProvider({ me, children }: { me: Me; children: ReactNode }) {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<string | null>(readStoredBusiness);

  const current =
    me.memberships.find((m) => m.business.id === selected) ?? me.memberships[0] ?? null;

  const selectBusiness = useCallback(
    (businessId: string) => {
      setSelected(businessId);
      try {
        window.localStorage.setItem(STORAGE_KEY, businessId);
      } catch {
        // Storage can be unavailable (private mode); selection still works for this tab.
      }
      void queryClient.invalidateQueries({ predicate: (q) => q.queryKey[0] === "business" });
    },
    [queryClient],
  );

  const refresh = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ["me"] });
  }, [queryClient]);

  const logout = useCallback(async () => {
    const { logout_url } = await api.post<{ logout_url: string }>("/auth/logout");
    setCsrfToken(null);
    window.location.assign(logout_url);
  }, []);

  const value = useMemo(
    () => ({ me, current, selectBusiness, refresh, logout }),
    [me, current, selectBusiness, refresh, logout],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}
