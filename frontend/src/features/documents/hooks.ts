import { useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { DocumentTypeInfo, InvoiceDocument } from "../../api/types";

export function useDocumentTypes(businessId: string) {
  return useQuery({
    queryKey: ["business", businessId, "document-types"],
    queryFn: () => api.get<DocumentTypeInfo[]>(`/businesses/${businessId}/document-types`),
    staleTime: 5 * 60_000,
  });
}

export function useDocument(businessId: string, documentId: string | undefined) {
  return useQuery({
    queryKey: ["business", businessId, "document", documentId],
    queryFn: () => api.get<InvoiceDocument>(`/businesses/${businessId}/documents/${documentId}`),
    enabled: Boolean(documentId),
  });
}

export function pdfUrl(businessId: string, documentId: string) {
  return `/api/v1/businesses/${businessId}/documents/${documentId}/pdf`;
}
