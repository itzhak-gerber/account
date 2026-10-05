import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { DocumentType } from "../../api/types";
import { errorMessage } from "../../lib/errors";
import { useDocumentTypes } from "../documents/hooks";

export function NumberingTab({ businessId, canEdit }: { businessId: string; canEdit: boolean }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const types = useDocumentTypes(businessId);
  const numbering = useQuery({
    queryKey: ["business", businessId, "numbering"],
    queryFn: () =>
      api.get<{ next_numbers: Record<DocumentType, number> }>(
        `/businesses/${businessId}/numbering`,
      ),
  });
  const [edits, setEdits] = useState<Partial<Record<DocumentType, string>>>({});
  const save = useMutation({
    mutationFn: (type: DocumentType) =>
      api.put(`/businesses/${businessId}/numbering`, { type, next_number: Number(edits[type]) }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["business", businessId, "numbering"] }),
  });

  return (
    <Card variant="outlined">
      <CardContent>
        <Typography color="text.secondary" sx={{ mb: 2 }}>
          {t("numbering.help")}
        </Typography>
        {save.isError && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {errorMessage(t, save.error)}
          </Alert>
        )}
        <Stack spacing={2}>
          {types.data?.map((info) => (
            <Stack key={info.type} direction="row" spacing={2} sx={{ alignItems: "center" }}>
              <Typography sx={{ flex: 1 }}>{info.title}</Typography>
              <TextField
                size="small"
                label={t("numbering.next")}
                value={edits[info.type] ?? String(numbering.data?.next_numbers[info.type] ?? "")}
                onChange={(e) =>
                  setEdits((v) => ({ ...v, [info.type]: e.target.value.replace(/\D/g, "") }))
                }
                disabled={!canEdit}
                sx={{ width: 140 }}
                slotProps={{ htmlInput: { dir: "ltr", inputMode: "numeric" } }}
              />
              {canEdit && (
                <Button
                  disabled={!edits[info.type] || save.isPending}
                  onClick={() => save.mutate(info.type)}
                >
                  {t("numbering.save")}
                </Button>
              )}
            </Stack>
          ))}
        </Stack>
      </CardContent>
    </Card>
  );
}
