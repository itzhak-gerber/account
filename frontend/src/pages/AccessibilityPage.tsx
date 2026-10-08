import Box from "@mui/material/Box";
import Container from "@mui/material/Container";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useEffect, type ReactNode } from "react";
import { Link as RouterLink } from "react-router";

import { ACCESSIBILITY } from "../config/accessibility";
import { formatDate } from "../lib/money";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Box component="section">
      <Typography variant="h5" component="h2" sx={{ fontWeight: 700, mb: 1 }}>
        {title}
      </Typography>
      {children}
    </Box>
  );
}

/** הצהרת נגישות – public, reachable without signing in. */
export function AccessibilityPage() {
  const { coordinator, updated } = ACCESSIBILITY;
  useEffect(() => {
    document.title = "הצהרת נגישות · חשבוניות";
  }, []);

  return (
    <Container component="main" maxWidth="md" sx={{ py: { xs: 3, md: 6 } }}>
      <Stack spacing={3}>
        <Link component={RouterLink} to="/">
          חזרה לחשבוניות
        </Link>
        <Typography variant="h3" component="h1" sx={{ fontWeight: 700 }}>
          הצהרת נגישות
        </Typography>
        <Typography>
          אנו רואים חשיבות רבה במתן שירות שוויוני לכלל המשתמשים, ובכלל זה לאנשים עם מוגבלות. המערכת
          הותאמה לדרישות תקנות שוויון זכויות לאנשים עם מוגבלות (התאמות נגישות לשירות), התשע״ג-2013,
          ולתקן הישראלי ת״י 5568 ברמה AA, המבוסס על הנחיות WCAG 2.0.
        </Typography>

        <Section title="מה הונגש">
          <Box component="ul" sx={{ m: 0, ps: 3, "& li": { mb: 0.5 } }}>
            <li>כל הפעולות במערכת זמינות במקלדת, עם סימון ברור של המיקום הנוכחי.</li>
            <li>קישור ״דילוג לתוכן הראשי״ בתחילת כל עמוד.</li>
            <li>תמיכה בקוראי מסך: כותרות, תוויות לשדות, הודעות שגיאה ותיאור לתרשימים.</li>
            <li>כותרת לכל עמוד, והעברת המיקוד לכותרת העמוד במעבר בין עמודים.</li>
            <li>ניגודיות צבעים של 4.5:1 לפחות בטקסט ובפקדים.</li>
            <li>התאמה למחשב ולטלפון, ותמיכה בהגדלת טקסט בדפדפן.</li>
            <li>מסמכי PDF מופקים כמסמכים מתויגים (PDF/UA), הניתנים לקריאה בקורא מסך.</li>
            <li>בדיקה אוטומטית של כל המסכים בכל עדכון גרסה.</li>
          </Box>
        </Section>

        <Section title="מגבלות ידועות">
          <Typography>
            מסמכי PDF שהופקו לפני עדכון הנגישות אינם מתויגים, ונשמרים כפי שהופקו (מסמך שהופק אינו
            ניתן לשינוי על פי דין). אם נתקלתם בחלק במערכת שאינו נגיש, נשמח לדעת ולתקן.
          </Typography>
        </Section>

        <Section title="פנייה בנושא נגישות">
          <Typography sx={{ mb: 1 }}>
            לשאלות, הערות או בקשה לקבלת מידע בפורמט נגיש, אפשר לפנות לרכז הנגישות:
          </Typography>
          {coordinator.name || coordinator.email || coordinator.phone ? (
            <Box component="ul" sx={{ m: 0, ps: 3 }}>
              {coordinator.name && <li>שם: {coordinator.name}</li>}
              {coordinator.phone && (
                <li>
                  טלפון:{" "}
                  <Link href={`tel:${coordinator.phone}`} dir="ltr">
                    {coordinator.phone}
                  </Link>
                </li>
              )}
              {coordinator.email && (
                <li>
                  דוא״ל:{" "}
                  <Link href={`mailto:${coordinator.email}`} dir="ltr">
                    {coordinator.email}
                  </Link>
                </li>
              )}
            </Box>
          ) : (
            <Typography color="text.secondary">פרטי הקשר של רכז הנגישות יפורסמו כאן.</Typography>
          )}
        </Section>

        <Typography variant="body2" color="text.secondary">
          ההצהרה עודכנה בתאריך {formatDate(updated)}.
        </Typography>
      </Stack>
    </Container>
  );
}
