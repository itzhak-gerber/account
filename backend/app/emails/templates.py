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


def _layout(body_html: str, *, logo_cid: str | None = None) -> str:
    return (
        '<!doctype html><html lang="he" dir="rtl"><body style="margin:0;background:#f5f7fb;'
        'font-family:Arial,sans-serif;color:#1f2937">'
        '<div style="max-width:560px;margin:24px auto;background:#fff;border-radius:10px;'
        'padding:24px;text-align:right">'
        + (
            f'<img src="cid:{logo_cid}" alt="" style="max-height:70px;max-width:220px;'
            'margin-bottom:16px">'
            if logo_cid
            else ""
        )
        + f"{body_html}"
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


def document_email(
    *,
    to: list[str],
    subject: str,
    message: str,
    business_name: str,
    title: str,
    number: int,
    total: str,
    logo_cid: str | None,
) -> tuple[str, str]:
    """HTML and plain-text bodies for a document sent to a customer."""
    paragraphs = "".join(
        f'<p style="margin:0 0 12px">{escape(p).replace(chr(10), "<br>")}</p>'
        for p in message.split("\n\n")
        if p.strip()
    )
    html = _layout(
        f"{paragraphs}"
        '<div style="background:#f5f7fb;border-radius:8px;padding:12px 16px;margin-top:16px">'
        f"<strong>{escape(title)} מס׳ {number}</strong><br>"
        f"סה״כ: {escape(total)} ₪<br>"
        '<span style="color:#6b7280">המסמך מצורף כקובץ PDF.</span></div>'
        f'<p style="color:#6b7280;margin-top:24px">{escape(business_name)}</p>',
        logo_cid=logo_cid,
    )
    text = f"{message}\n\n{title} מס׳ {number} – סה״כ {total} ₪ (מצורף כקובץ PDF)\n{business_name}"
    return html, text


def notification_email(
    *,
    to: str,
    business_name: str | None,
    title: str,
    link: str,
    details: tuple[tuple[str, str], ...] = (),
    intro: str | None = None,
) -> Email:
    """A short alert pointing back to the app. Alerts carry no amounts or customer details;
    only summaries the user chose to receive by email (``details``) include figures."""
    subject = f"{title} · {business_name}" if business_name else title
    intro = intro or (f"התראה חדשה בעסק {business_name}." if business_name else "")
    rows = "".join(
        f'<tr><td style="padding:6px 0;color:#6b7280">{escape(label)}</td>'
        f'<td style="padding:6px 12px;font-weight:bold">{escape(value)}</td></tr>'
        for label, value in details
    )
    table = f'<table style="border-collapse:collapse;margin:8px 0 16px">{rows}</table>'
    html = _layout(
        f'<h2 style="margin-top:0">{escape(title)}</h2>'
        + (f"<p>{escape(intro)}</p>" if intro else "")
        + (table if rows else "")
        + f'<p><a href="{escape(link)}" style="display:inline-block;background:#1e4fd8;color:#fff;'
        'padding:12px 20px;border-radius:8px;text-decoration:none">לפרטים במערכת</a></p>'
        '<p style="color:#6b7280">אפשר לבחור אילו התראות יגיעו במייל במסך "פרופיל ואבטחה".</p>'
    )
    text = (
        f"{title}\n{intro}\n"
        + "".join(f"{label}: {value}\n" for label, value in details)
        + f"לפרטים: {link}\n\n"
        'אפשר לבחור אילו התראות יגיעו במייל במסך "פרופיל ואבטחה".'
    )
    return Email(to=to, subject=subject, html=html, text=text)
