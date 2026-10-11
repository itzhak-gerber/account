"""Digital signature on issued documents' PDFs (חתימה אלקטרונית מאובטחת).

A computerised invoice sent electronically must carry a secure electronic signature, so any
change after issue is detectable. Every PDF of an issued document (the original and each copy)
is signed with the business software's certificate: a PAdES certification signature that allows
no later changes, optionally with a trusted timestamp from the certificate authority.

The certificate comes as a PKCS#12 file (base64) with its password, both from Key Vault. Without
one, PDFs are produced unsigned (development, or before a certificate is bought).
"""

import base64
import io
from functools import lru_cache

import structlog
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import fields, signers, timestamps

from app.core.config import get_settings

log = structlog.get_logger()
UNSET = ("", "unset")


def enabled() -> bool:
    return get_settings().pdf_signing_p12 not in UNSET


@lru_cache(maxsize=2)
def _signer(p12_b64: str, password: str) -> signers.SimpleSigner:
    signer: signers.SimpleSigner | None = signers.SimpleSigner.load_pkcs12_data(
        base64.b64decode(p12_b64), other_certs=(), passphrase=password.encode() or None
    )
    if signer is None:
        raise ValueError("The signing certificate could not be read")
    return signer


async def sign(pdf: bytes) -> bytes:
    """The PDF with a certification signature, or unchanged when signing is not set up."""
    settings = get_settings()
    if not enabled():
        return pdf
    password = "" if settings.pdf_signing_password in UNSET else settings.pdf_signing_password
    signer = _signer(settings.pdf_signing_p12, password)
    timestamper = (
        timestamps.HTTPTimeStamper(settings.pdf_signing_tsa_url, timeout=10)
        if settings.pdf_signing_tsa_url
        else None
    )
    meta = signers.PdfSignatureMetadata(
        field_name="Signature1",
        md_algorithm="sha256",
        subfilter=fields.SigSeedSubFilter.PADES,
        reason="מסמך ממוחשב חתום – כל שינוי בו יבטל את החתימה",
        certify=True,
        docmdp_permissions=fields.MDPPerm.NO_CHANGES,
    )
    out = await signers.async_sign_pdf(
        IncrementalPdfFileWriter(io.BytesIO(pdf)), meta, signer=signer, timestamper=timestamper
    )
    signed: bytes = out.getvalue()
    return signed
