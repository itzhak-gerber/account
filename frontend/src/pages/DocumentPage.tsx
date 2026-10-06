import CircularProgress from "@mui/material/CircularProgress";
import { useTranslation } from "react-i18next";
import { useParams, useSearchParams } from "react-router";

import type { DocumentType } from "../api/types";
import { useSession } from "../auth/context";
import { DocumentEditor } from "../features/documents/DocumentEditor";
import { DocumentView } from "../features/documents/DocumentView";
import { useDocument, useDocumentTypes } from "../features/documents/hooks";

export function DocumentPage() {
  const { t } = useTranslation();
  const { documentId } = useParams();
  const [params] = useSearchParams();
  const { current } = useSession();
  const businessId = current!.business.id;
  const types = useDocumentTypes(businessId);
  const isNew = documentId === "new";
  const document = useDocument(businessId, isNew ? undefined : documentId);
  const payInvoiceId = isNew ? (params.get("invoice") ?? undefined) : undefined;
  const payInvoice = useDocument(businessId, payInvoiceId);

  if (types.isPending || (!isNew && document.isPending) || (payInvoiceId && payInvoice.isPending))
    return <CircularProgress />;
  if (!isNew && !document.data) return <>{t("errors.document_not_found")}</>;

  const type = (isNew ? params.get("type") : document.data!.type) as DocumentType;
  const info = types.data?.find((i) => i.type === type);
  if (!info) return <>{t("errors.document_type_not_allowed")}</>;

  if (!isNew && document.data!.status === "issued") {
    return <DocumentView businessId={businessId} doc={document.data!} />;
  }
  return (
    <DocumentEditor
      key={document.data?.id ?? "new"}
      businessId={businessId}
      type={type}
      info={info}
      document={isNew ? null : document.data!}
      payInvoice={payInvoice.data ?? null}
    />
  );
}
