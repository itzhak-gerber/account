"""Hebrew (right-to-left) email templates."""

from dataclasses import dataclass
from html import escape

from app.models import Role

ROLE_LABELS_HE = {
    Role.OWNER: "בעלים",
    Role.ADMIN: "מנהל/ת",
    Role.ACCOUNTANT: "רואה חשבון",
    Role.MEMBER: "משתמש/ת",
    Role.VIEWER: "צפייה בלבד",
}


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    html: str
    text: str


def _layout(body_html: str) -> str:
    return (
        '<!doctype html><html lang="he" dir="rtl"><body style="margin:0;background:#f5f7fb;'
        'font-family:Arial,sans-serif;color:#1f2937">'
        '<div style="max-width:560px;margin:24px auto;background:#fff;border-radius:10px;'
        'padding:24px;text-align:right">'
        f"{body_html}"
        '<p style="color:#6b7280;font-size:12px;margin-top:32px">'
        "הודעה זו נשלחה אוטומטית ממערכת חשבוניות.</p></div></body></html>"
    )


def invitation_email(
    *, to: str, business_name: str, invited_by: str, role: Role, link: str, ttl_days: int
) -> Email:
    role_he = ROLE_LABELS_HE[role]
    subject = f"הזמנה להצטרף ל{business_name}"
    html = _layout(
        f'<h2 style="margin-top:0">{escape(subject)}</h2>'
        f"<p>{escape(invited_by)} הזמין/ה אותך להצטרף לעסק <strong>{escape(business_name)}</strong>"
        f" בתפקיד <strong>{escape(role_he)}</strong>.</p>"
        f'<p><a href="{escape(link)}" style="display:inline-block;background:#1e4fd8;color:#fff;'
        'padding:12px 20px;border-radius:8px;text-decoration:none">קבלת ההזמנה</a></p>'
        f'<p style="color:#6b7280">ההזמנה בתוקף ל-{ttl_days} ימים. '
        "אם לא ציפית להזמנה, אפשר להתעלם מהודעה זו.</p>"
    )
    text = (
        f"{invited_by} הזמין/ה אותך להצטרף לעסק {business_name} בתפקיד {role_he}.\n"
        f"לקבלת ההזמנה: {link}\nההזמנה בתוקף ל-{ttl_days} ימים."
    )
    return Email(to=to, subject=subject, html=html, text=text)
