import DeleteOutlined from "@mui/icons-material/DeleteOutlined";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import IconButton from "@mui/material/IconButton";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { Invitation, Member, Role } from "../../api/types";
import { useSession } from "../../auth/context";
import { can } from "../../auth/permissions";
import { errorMessage } from "../../lib/errors";

const ROLES: Role[] = ["owner", "admin", "accountant", "member", "viewer"];

export function TeamTab({ businessId, role }: { businessId: string; role: Role }) {
  const { t } = useTranslation();
  const { me, refresh } = useSession();
  const queryClient = useQueryClient();
  const base = `/businesses/${businessId}`;
  const canManage = can(role, "manageMembers");
  const assignable = ROLES.filter((r) => r !== "owner" || can(role, "manageOwners"));

  const members = useQuery({
    queryKey: ["business", businessId, "members"],
    queryFn: () => api.get<Member[]>(`${base}/members`),
  });
  const invitations = useQuery({
    queryKey: ["business", businessId, "invitations"],
    queryFn: () => api.get<Invitation[]>(`${base}/invitations`),
    enabled: canManage,
  });
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["business", businessId] });

  const changeRole = useMutation({
    mutationFn: ({ id, newRole }: { id: string; newRole: Role }) =>
      api.patch<Member[]>(`${base}/members/${id}`, { role: newRole }),
    onSettled: invalidate,
  });
  const remove = useMutation({
    mutationFn: (id: string) => api.delete(`${base}/members/${id}`),
    onSuccess: async (_, id) => {
      const self = members.data?.find((m) => m.id === id)?.user_id === me.user.id;
      if (self) await refresh();
    },
    onSettled: invalidate,
  });
  const revoke = useMutation({
    mutationFn: (id: string) => api.delete(`${base}/invitations/${id}`),
    onSettled: invalidate,
  });

  const [email, setEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<Role>("member");
  const invite = useMutation({
    mutationFn: () => api.post<Invitation>(`${base}/invitations`, { email, role: inviteRole }),
    onSuccess: () => setEmail(""),
    onSettled: invalidate,
  });
  const submitInvite = (e: FormEvent) => {
    e.preventDefault();
    if (email.trim()) invite.mutate();
  };

  const mutationError = changeRole.error ?? remove.error ?? revoke.error;

  return (
    <Stack spacing={3}>
      {mutationError && <Alert severity="error">{errorMessage(t, mutationError)}</Alert>}
      <Card variant="outlined">
        <CardContent>
          <Typography variant="h6" component="h2" gutterBottom>
            {t("team.members")}
          </Typography>
          <List disablePadding>
            {members.data?.map((m) => {
              const isSelf = m.user_id === me.user.id;
              const ownerCount = members.data?.filter((x) => x.role === "owner").length ?? 0;
              const isLastOwner = m.role === "owner" && ownerCount <= 1;
              const editable =
                canManage && !isSelf && (m.role !== "owner" || can(role, "manageOwners"));
              return (
                <ListItem
                  key={m.id}
                  divider
                  disableGutters
                  sx={{ flexWrap: "wrap", gap: 1 }}
                  secondaryAction={
                    (editable || isSelf) &&
                    !isLastOwner && (
                      <Tooltip title={isSelf ? t("team.leave") : t("team.remove")}>
                        <IconButton
                          edge="end"
                          aria-label={isSelf ? t("team.leave") : t("team.remove")}
                          onClick={() => {
                            if (
                              window.confirm(
                                t("team.confirmRemove", { name: m.full_name || m.email }),
                              )
                            )
                              remove.mutate(m.id);
                          }}
                        >
                          <DeleteOutlined />
                        </IconButton>
                      </Tooltip>
                    )
                  }
                >
                  <ListItemText
                    primary={`${m.full_name || m.email}${isSelf ? ` ${t("team.you")}` : ""}`}
                    secondary={<span dir="ltr">{m.email}</span>}
                    sx={{ minWidth: 200, flex: "1 1 200px" }}
                  />
                  <TextField
                    select
                    size="small"
                    label={t("team.role")}
                    value={m.role}
                    disabled={!editable || changeRole.isPending}
                    onChange={(e) =>
                      changeRole.mutate({ id: m.id, newRole: e.target.value as Role })
                    }
                    sx={{ minWidth: 150, me: 6 }}
                  >
                    {(editable ? assignable : ROLES).map((r) => (
                      <MenuItem key={r} value={r}>
                        {t(`roles.${r}`)}
                      </MenuItem>
                    ))}
                  </TextField>
                </ListItem>
              );
            })}
          </List>
        </CardContent>
      </Card>

      {canManage && (
        <Card variant="outlined">
          <CardContent>
            <Typography variant="h6" component="h2" gutterBottom>
              {t("team.invite")}
            </Typography>
            {invite.isError && (
              <Alert severity="error" sx={{ mb: 2 }}>
                {errorMessage(t, invite.error)}
              </Alert>
            )}
            {invite.isSuccess && (
              <Alert severity="success" sx={{ mb: 2 }}>
                {t("team.sent", { email: invite.data.email })}
              </Alert>
            )}
            <form onSubmit={submitInvite}>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                <TextField
                  label={t("team.inviteEmail")}
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  slotProps={{ htmlInput: { dir: "ltr" } }}
                  sx={{ flex: 2 }}
                />
                <TextField
                  select
                  label={t("team.inviteRole")}
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value as Role)}
                  helperText={t(`roleHelp.${inviteRole}`)}
                  sx={{ flex: 1, minWidth: 160 }}
                >
                  {assignable.map((r) => (
                    <MenuItem key={r} value={r}>
                      {t(`roles.${r}`)}
                    </MenuItem>
                  ))}
                </TextField>
                <Button
                  type="submit"
                  variant="contained"
                  disabled={invite.isPending}
                  sx={{ height: 56 }}
                >
                  {t("team.send")}
                </Button>
              </Stack>
            </form>

            <Typography variant="subtitle1" component="h3" sx={{ mt: 3, fontWeight: 500 }}>
              {t("team.pending")}
            </Typography>
            {invitations.data?.length === 0 && (
              <Typography color="text.secondary">{t("team.noPending")}</Typography>
            )}
            <List disablePadding>
              {invitations.data?.map((inv) => (
                <ListItem
                  key={inv.id}
                  divider
                  disableGutters
                  secondaryAction={
                    <Button color="error" onClick={() => revoke.mutate(inv.id)}>
                      {t("team.revoke")}
                    </Button>
                  }
                >
                  <ListItemText
                    primary={<span dir="ltr">{inv.email}</span>}
                    secondary={`${t(`roles.${inv.role}`)} · ${t("team.expires")} ${new Date(
                      inv.expires_at,
                    ).toLocaleDateString("he-IL")}`}
                  />
                </ListItem>
              ))}
            </List>
          </CardContent>
        </Card>
      )}
    </Stack>
  );
}
