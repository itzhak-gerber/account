import { createContext, useContext } from "react";

import type { Me, Membership } from "../api/types";

export interface SessionValue {
  me: Me;
  current: Membership | null;
  selectBusiness: (businessId: string) => void;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
}

export const SessionContext = createContext<SessionValue | null>(null);

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession must be used inside SessionProvider");
  return value;
}
