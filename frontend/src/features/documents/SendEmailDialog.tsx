import Alert from "@mui/material/Alert";
import Autocomplete from "@mui/material/Autocomplete";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { Delivery, EmailDefaults } from "../../api/types";
import { errorMessage } from "../../lib/errors";

interface Props {
  businessId: string;
  documentId: string;
  originalSent: boolean;
  onClose: () => void;
}

function EmailForm({
  defaults,
  businessId,
  documentId,
  originalSent,
  onClose,
}: Props & { defaults: EmailDefaults }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [to, setTo] = useState<string[]>(defaults.to);
  const [pending, setPending] = useState("");
  const [subject, setSubject] = useState(defaults.subject);
  const [message, setMessage] = useState(defaults.message);
  const send = useMutation({
    mutationFn: (recipients: string[]) =>
      api.post<Delivery>(`/businesses/${businessId}/documents/${documentId}/send-email`, {
        to: recipients,
        subject,
        message,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["business", businessId, "document", documentId],
      });
      onClose();
    },
  });
  // A typed address that was not yet confirmed with Enter still counts.
  const recipients = [...to, ...(pending.trim() ? [pending.trim()] : [])];

  return (
    <>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          {send.isError && <Alert severity="error">{errorMessage(t, send.error)}</Alert>}
          <Autocomplete<string, true, false, true>
            multiple
            freeSolo
            options={[]}
            value={to}
            inputValue={pending}
            onInputChange={(_, value) => setPending(value)}
            onChange={(_, value) =>
              setTo(
                value
                  .map((v) => v.trim())
                  .filter(Boolean)
                  .slice(0, 5),
              )
            }
            renderValue={(values, getItemProps) =>
              values.map((email, index) => {
                const { key, ...props } = getItemProps({ index });
                return <Chip key={key} label={email} dir="ltr" size="small" {...props} />;
              })
            }
            renderInput={(params) => (
              <TextField {...params} label={t("email.to")} helperText={t("email.toHelp")} />
            )}
          />
          <TextField
            label={t("email.subject")}
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
          />
          <TextField
            label={t("email.message")}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            multiline
            minRows={5}
          />
          {!originalSent && (
            <Typography variant="body2" color="text.secondary">
              {t("email.originalNote")}
            </Typography>
          )}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose}>{t("common.cancel")}</Button>
        <Button
          variant="contained"
          disabled={send.isPending || recipients.length === 0 || !subject.trim()}
          onClick={() => send.mutate(recipients.slice(0, 5))}
        >
          {t("email.submit")}
        </Button>
      </DialogActions>
    </>
  );
}

export function SendEmailDialog(props: Props) {
  const { t } = useTranslation();
  const fullScreen = useMediaQuery(useTheme().breakpoints.down("sm"));
  const defaults = useQuery({
    queryKey: ["business", props.businessId, "email-defaults", props.documentId],
    queryFn: () =>
      api.get<EmailDefaults>(
        `/businesses/${props.businessId}/documents/${props.documentId}/email-defaults`,
      ),
    staleTime: 0,
  });
  return (
    <Dialog open onClose={props.onClose} fullScreen={fullScreen} maxWidth="sm" fullWidth>
      <DialogTitle>{t("email.title")}</DialogTitle>
      {defaults.data && <EmailForm {...props} defaults={defaults.data} />}
    </Dialog>
  );
}
