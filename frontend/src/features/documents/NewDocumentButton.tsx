import AddIcon from "@mui/icons-material/Add";
import Button from "@mui/material/Button";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import { useSession } from "../../auth/context";
import { can } from "../../auth/permissions";
import { useDocumentTypes } from "./hooks";

export function NewDocumentButton({ fullWidth }: { fullWidth?: boolean }) {
  const { t } = useTranslation();
  const { current } = useSession();
  const navigate = useNavigate();
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const types = useDocumentTypes(current!.business.id);
  if (!can(current?.role, "editDocuments")) return null;

  return (
    <>
      <Button
        variant="contained"
        size="large"
        startIcon={<AddIcon />}
        fullWidth={fullWidth}
        onClick={(e) => setAnchor(e.currentTarget)}
        aria-haspopup="menu"
      >
        {t("documents.new")}
      </Button>
      <Menu anchorEl={anchor} open={anchor !== null} onClose={() => setAnchor(null)}>
        {types.data
          ?.filter((info) => info.type !== "credit_note")
          .map((info) => (
            <MenuItem
              key={info.type}
              onClick={() => {
                setAnchor(null);
                void navigate(`/documents/new?type=${info.type}`);
              }}
            >
              {info.title}
            </MenuItem>
          ))}
      </Menu>
    </>
  );
}
