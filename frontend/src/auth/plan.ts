import type { Membership, ModuleName } from "../api/types";
import { can } from "./permissions";

/** Mirrors the business's plan, only to show or lock controls; the server always decides. */
export function hasModule(current: Membership | null | undefined, module: ModuleName): boolean {
  const plan = current?.plan;
  if (!plan) return true; // no plan information: as before plans
  return !plan.read_only && plan.modules.includes(module);
}

export function isReadOnly(current: Membership | null | undefined): boolean {
  return current?.plan?.read_only ?? false;
}

/** A role's right to change data, which a read-only business (plan ended) does not have. */
export function canChange(
  current: Membership | null | undefined,
  action: "manageCatalog" | "editDocuments" | "managePurchasing",
): boolean {
  return can(current?.role, action) && !isReadOnly(current);
}
