"""Issued documents' PDFs carry a certification signature that exposes any later change."""

import base64
import io
from datetime import UTC, datetime, timedelta

import pytest
from asn1crypto import x509 as asn1_x509  # type: ignore[import-untyped]
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign.fields import MDPPerm
from pyhanko.sign.validation import async_validate_pdf_signature
from pyhanko_certvalidator import ValidationContext

from app.core.config import get_settings
from app.pdf import signing
from tests.fake_idp import FakeIdP
from tests.helpers import app_client
from tests.test_documents import draft, issue, setup


@pytest.fixture
def certificate(monkeypatch: pytest.MonkeyPatch) -> asn1_x509.Certificate:
    """A self-signed test certificate in place of the one bought from a certificate authority."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Invoice test signer")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=True,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    p12 = pkcs12.serialize_key_and_certificates(
        b"test", key, cert, None, serialization.BestAvailableEncryption(b"pw")
    )
    settings = get_settings()
    monkeypatch.setattr(settings, "pdf_signing_p12", base64.b64encode(p12).decode())
    monkeypatch.setattr(settings, "pdf_signing_password", "pw")
    signing._signer.cache_clear()
    return asn1_x509.Certificate.load(cert.public_bytes(serialization.Encoding.DER))


async def check(pdf: bytes, root: asn1_x509.Certificate) -> tuple[bool, bool]:
    [signature] = PdfFileReader(io.BytesIO(pdf)).embedded_signatures
    assert signature.docmdp_level == MDPPerm.NO_CHANGES  # certified: no changes allowed
    status = await async_validate_pdf_signature(signature, ValidationContext(trust_roots=[root]))
    return status.intact, status.valid


async def test_original_and_copies_are_signed(
    idp: FakeIdP, certificate: asn1_x509.Certificate
) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        invoice = await draft(owner, bid)
        base = f"/api/v1/businesses/{bid}/documents/{invoice['id']}/pdf"

        preview = await owner.get(base)  # a draft preview is not a document
        assert b"/ByteRange" not in preview.content

        assert (await issue(owner, bid, invoice["id"])).status_code == 200
        original = (await owner.get(base)).content
        copy = (await owner.get(base, params={"variant": "copy"})).content
        for pdf in (original, copy):
            assert pdf.startswith(b"%PDF")
            assert await check(pdf, certificate) == (True, True)

        # One changed byte inside the signed range: the signature no longer matches.
        at = original.index(b"/Type /Page") + 2
        tampered = original[:at] + bytes([original[at] ^ 0x01]) + original[at + 1 :]
        assert (await check(tampered, certificate))[0] is False


def test_off_without_a_certificate() -> None:
    assert not signing.enabled()
