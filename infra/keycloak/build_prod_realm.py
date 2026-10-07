"""Build the production realm (realm-invoice.json) from the development one.

    python infra/keycloak/build_prod_realm.py          # write realm-invoice.json
    python infra/keycloak/build_prod_realm.py --check  # fail if it is out of date (CI)

Same login flows, theme, two-factor and password policies as development, minus everything
that only exists for local testing: the demo users, the password-grant CLI client and the
Mailpit mail server. URLs, the client secret and the mail server come from environment
variables, which Keycloak fills in when it imports the realm on first start.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
DEV = HERE / "realm-invoice.dev.json"
PROD = HERE / "realm-invoice.json"


def build() -> dict:
    realm = json.loads(DEV.read_text(encoding="utf-8"))
    realm.pop("users", None)
    realm["clients"] = [c for c in realm["clients"] if c["clientId"] != "invoice-dev-cli"]
    for client in realm["clients"]:
        if client["clientId"] == "invoice-web":
            client["secret"] = "${INVOICE_WEB_CLIENT_SECRET}"
            client["redirectUris"] = ["${APP_PUBLIC_URL}/auth/callback"]
            client["webOrigins"] = []
            client.setdefault("attributes", {})["post.logout.redirect.uris"] = (
                "${APP_PUBLIC_URL}/*"
            )
    realm["sslRequired"] = "external"
    realm["smtpServer"] = {
        "host": "${SMTP_HOST}",
        "port": "${SMTP_PORT}",
        "starttls": "true",
        "auth": "true",
        "user": "${SMTP_USERNAME}",
        "password": "${SMTP_PASSWORD}",
        "from": "${SMTP_FROM}",
        "fromDisplayName": realm["smtpServer"].get("fromDisplayName", ""),
    }
    return realm


def main() -> int:
    text = json.dumps(build(), ensure_ascii=False, indent=2) + "\n"
    if "--check" in sys.argv:
        if PROD.read_text(encoding="utf-8") != text:
            print("realm-invoice.json is out of date: run infra/keycloak/build_prod_realm.py")
            return 1
        return 0
    PROD.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
