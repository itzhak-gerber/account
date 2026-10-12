import Alert from "@mui/material/Alert";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import FormControl from "@mui/material/FormControl";
import FormControlLabel from "@mui/material/FormControlLabel";
import FormHelperText from "@mui/material/FormHelperText";
import FormLabel from "@mui/material/FormLabel";
import Radio from "@mui/material/Radio";
import RadioGroup from "@mui/material/RadioGroup";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { Me, TextSize, ThemePreference, User } from "../../api/types";
import { useSession } from "../../auth/context";
import { errorMessage } from "../../lib/errors";

const THEMES: ThemePreference[] = ["system", "light", "dark"];
const SIZES: TextSize[] = ["device", "large", "xlarge"];

type Change = Partial<Pick<User, "theme" | "text_size">>;

/** Light / dark / device theme and text size. Applied at once, saved to the user's profile. */
export function DisplayCard() {
  const { t } = useTranslation();
  const { me } = useSession();
  const queryClient = useQueryClient();
  const setUser = (user: User) =>
    queryClient.setQueryData<Me | null>(["me"], (old) => (old ? { ...old, user } : old));

  const save = useMutation({
    mutationFn: (change: Change) => api.patch<User>("/me/display-preferences", change),
    onMutate: (change) => {
      const before = me.user;
      setUser({ ...before, ...change });
      return { before };
    },
    onError: (_error, _change, context) => {
      if (context) setUser(context.before);
    },
    onSuccess: setUser,
  });

  return (
    <Card variant="outlined" id="display">
      <CardContent>
        <Stack spacing={2}>
          <Typography variant="h6" component="h2">
            {t("display.title")}
          </Typography>
          <FormControl>
            <FormLabel id="display-theme">{t("display.theme")}</FormLabel>
            <RadioGroup
              row
              aria-labelledby="display-theme"
              value={me.user.theme}
              onChange={(_e, value) => save.mutate({ theme: value as ThemePreference })}
            >
              {THEMES.map((value) => (
                <FormControlLabel
                  key={value}
                  value={value}
                  control={<Radio />}
                  label={t(`display.themes.${value}`)}
                />
              ))}
            </RadioGroup>
          </FormControl>
          <FormControl>
            <FormLabel id="display-size">{t("display.textSize")}</FormLabel>
            <RadioGroup
              row
              aria-labelledby="display-size"
              aria-describedby="display-size-help"
              value={me.user.text_size}
              onChange={(_e, value) => save.mutate({ text_size: value as TextSize })}
            >
              {SIZES.map((value) => (
                <FormControlLabel
                  key={value}
                  value={value}
                  control={<Radio />}
                  label={t(`display.sizes.${value}`)}
                />
              ))}
            </RadioGroup>
            <FormHelperText id="display-size-help" sx={{ mx: 0 }}>
              {t("display.textSizeHelp")}
            </FormHelperText>
          </FormControl>
          {save.isError && <Alert severity="error">{errorMessage(t, save.error)}</Alert>}
        </Stack>
      </CardContent>
    </Card>
  );
}
