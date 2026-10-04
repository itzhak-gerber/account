import type { BusinessInput } from "../../api/types";

export const EMPTY_BUSINESS: BusinessInput = {
  legal_name: "",
  display_name: "",
  tax_id: "",
  business_type: "licensed_dealer",
  address_street: "",
  address_city: "",
  address_zip: "",
  phone: "",
  email: "",
};
