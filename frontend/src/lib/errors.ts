import type { TFunction } from "i18next";

import { ApiError } from "../api/client";

export function errorMessage(t: TFunction, error: unknown): string {
  if (error instanceof ApiError) {
    const key = `errors.${error.code}`;
    const text = t(key);
    return text === key ? t("errors.unknown_error") : text;
  }
  return t("errors.unknown_error");
}

export function isMfaRequired(error: unknown): boolean {
  return error instanceof ApiError && error.code === "mfa_required";
}
