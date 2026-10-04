export type Role = "owner" | "admin" | "accountant" | "member" | "viewer";
export type BusinessType = "exempt_dealer" | "licensed_dealer" | "company" | "nonprofit";

export interface User {
  id: string;
  email: string;
  full_name: string;
}

export interface Business {
  id: string;
  legal_name: string;
  display_name: string;
  tax_id: string;
  business_type: BusinessType;
  address_street: string;
  address_city: string;
  address_zip: string;
  phone: string;
  email: string;
  default_currency: string;
}

export interface Membership {
  business: Business;
  role: Role;
}

export interface Me {
  user: User;
  memberships: Membership[];
  mfa: boolean;
  csrf_token: string | null;
}

export interface Member {
  id: string;
  user_id: string;
  email: string;
  full_name: string;
  role: Role;
  joined_at: string;
}

export interface Invitation {
  id: string;
  email: string;
  role: Role;
  expires_at: string;
  created_at: string;
}

export interface InvitationPreview {
  business_name: string;
  invited_by_name: string;
  email: string;
  role: Role;
  expires_at: string;
  status: "pending" | "expired" | "accepted" | "revoked";
}

export interface AuditEntry {
  id: string;
  actor_email: string | null;
  actor_channel: "web" | "api" | "mcp" | "system";
  action: string;
  entity_type: string;
  changes: Record<string, unknown>;
  ip: string | null;
  created_at: string;
}

export type BusinessInput = Omit<Business, "id" | "default_currency" | "email"> & {
  email: string | null;
};
