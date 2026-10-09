import type { Membership } from "../api/types";

const ROLE_RANK = { owner: 5, admin: 4, accountant: 3, member: 2, viewer: 1 } as const;

/** Mirrors the backend permission table, only to hide controls; the server always decides. */
export function can(
  role: Membership["role"] | undefined,
  action:
    | "manageBusiness"
    | "manageMembers"
    | "manageOwners"
    | "viewMembers"
    | "viewAudit"
    | "manageCatalog"
    | "editDocuments"
    | "viewReports"
    | "viewPurchasing"
    | "managePurchasing"
    | "exportData",
): boolean {
  if (!role) return false;
  switch (action) {
    case "manageBusiness":
    case "manageMembers":
      return ROLE_RANK[role] >= ROLE_RANK.admin;
    case "manageOwners":
      return role === "owner";
    case "viewMembers":
      return role !== "viewer";
    case "manageCatalog":
    case "editDocuments":
    case "managePurchasing":
      return role === "owner" || role === "admin" || role === "member";
    case "viewReports":
    case "viewPurchasing":
      return role !== "viewer";
    case "viewAudit":
    case "exportData":
      return role === "owner" || role === "admin" || role === "accountant";
  }
}
