import SearchIcon from "@mui/icons-material/Search";
import InputAdornment from "@mui/material/InputAdornment";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import { useQuery } from "@tanstack/react-query";
import { useDeferredValue, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import type { DocumentStatus, DocumentSummary, DocumentType } from "../api/types";
import { useSession } from "../auth/context";
import { DocumentList } from "../features/documents/DocumentList";
import { NewDocumentButton } from "../features/documents/NewDocumentButton";
import { useDocumentTypes } from "../features/documents/hooks";

export function DocumentsPage() {
  const { t } = useTranslation();
  const { current } = useSession();
  const businessId = current!.business.id;
  const types = useDocumentTypes(businessId);
  const [type, setType] = useState<DocumentType | "">("");
  const [status, setStatus] = useState<DocumentStatus | "">("");
  const [search, setSearch] = useState("");
  const q = useDeferredValue(search);

  const params = new URLSearchParams({ limit: "100" });
  if (type) params.set("type", type);
  if (status) params.set("status", status);
  if (q) params.set("q", q);
  const documents = useQuery({
    queryKey: ["business", businessId, "documents", params.toString()],
    queryFn: () => api.get<DocumentSummary[]>(`/businesses/${businessId}/documents?${params}`),
  });

  return (
    <Stack spacing={3} sx={{ maxWidth: 960 }}>
      <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", gap: 2 }}>
        <Typography variant="h4" component="h1" sx={{ fontWeight: 700 }}>
          {t("documents.title")}
        </Typography>
        <NewDocumentButton />
      </Stack>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
        <TextField
          placeholder={t("documents.search")}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          sx={{ flex: 2 }}
          slotProps={{
            input: {
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon />
                </InputAdornment>
              ),
            },
          }}
        />
        <TextField
          select
          value={type}
          onChange={(e) => setType(e.target.value as DocumentType | "")}
          sx={{ flex: 1, minWidth: 180 }}
          slotProps={{ select: { displayEmpty: true } }}
        >
          <MenuItem value="">{t("documents.allTypes")}</MenuItem>
          {types.data?.map((info) => (
            <MenuItem key={info.type} value={info.type}>
              {info.title}
            </MenuItem>
          ))}
        </TextField>
        <ToggleButtonGroup
          exclusive
          value={status}
          onChange={(_, value: DocumentStatus | "" | null) => setStatus(value ?? "")}
          size="small"
        >
          <ToggleButton value="">{t("documents.allStatuses")}</ToggleButton>
          <ToggleButton value="issued">{t("docStatus.issued")}</ToggleButton>
          <ToggleButton value="draft">{t("docStatus.draft")}</ToggleButton>
        </ToggleButtonGroup>
      </Stack>
      <DocumentList documents={documents.data} empty={t("documents.empty")} />
    </Stack>
  );
}
