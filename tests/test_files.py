"""What a file is, before it becomes a secret (spec/008, R5)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import pkcs12

from caland.application.files import LIMIT, describe

EXPIRES = datetime(2027, 1, 14, 12, 0, 0, tzinfo=UTC)


def certificate(
    names=("api.example.com",), common="api.example.com", issuer="Example CA"
):
    key = ec.generate_private_key(ec.SECP256R1())
    builder = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, common)]))
        .issuer_name(x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, issuer)]))
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime(2026, 1, 1, tzinfo=UTC))
        .not_valid_after(EXPIRES)
    )
    if names:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.DNSName(name) for name in names]), False
        )
    return builder.sign(key, hashes.SHA256()), key


def pem(cert) -> bytes:
    return cert.public_bytes(serialization.Encoding.PEM)


def key_pem(key, password: bytes | None = None) -> bytes:
    how = (
        serialization.BestAvailableEncryption(password)
        if password
        else serialization.NoEncryption()
    )
    return key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, how
    )


def test_a_pem_certificate_says_who_it_is_for_who_issued_it_and_when_it_ends():
    cert, _ = certificate()
    told = describe(pem(cert))
    assert told.kind == "PEM certificate" and told.binary is False
    assert told.facts == (("For", "api.example.com"), ("Issued by", "Example CA"))
    assert told.expires == "2027-01-14T12:00:00Z"
    assert told.size == len(pem(cert))


def test_the_names_it_lists_count_before_its_subject():
    cert, _ = certificate(
        names=("a.example", "b.example", "c.example", "d.example", "e.example")
    )
    assert (
        dict(describe(pem(cert)).facts)["For"]
        == "a.example, b.example, c.example and 2 more"
    )
    cert, _ = certificate(names=(), common="only the subject")
    assert dict(describe(pem(cert)).facts)["For"] == "only the subject"


def test_a_chain_is_counted_and_described_by_its_first():
    leaf, _ = certificate()
    root, _ = certificate(names=("root.example",), common="root")
    told = describe(pem(leaf) + pem(root))
    assert told.kind == "PEM certificate chain (2)"
    assert dict(told.facts)["For"] == "api.example.com"


def test_a_certificate_with_its_key_says_so():
    cert, key = certificate()
    assert (
        describe(pem(cert) + key_pem(key)).kind == "PEM certificate with its private key"
    )


def test_a_private_key_is_named_and_never_read():
    _, key = certificate()
    assert describe(key_pem(key)).kind == "PEM private key"
    assert describe(key_pem(key, b"hunter2")).kind == "PEM private key, encrypted"
    assert describe(key_pem(key)).facts == ()


def test_a_der_certificate_is_binary_and_read():
    cert, _ = certificate()
    told = describe(cert.public_bytes(serialization.Encoding.DER))
    assert told.kind == "DER certificate" and told.binary is True
    assert dict(told.facts)["Issued by"] == "Example CA" and told.expires


def test_a_pkcs12_bundle_with_a_password_is_named_and_not_opened():
    cert, key = certificate()
    data = pkcs12.serialize_key_and_certificates(
        b"prod", key, cert, None, serialization.BestAvailableEncryption(b"hunter2")
    )
    told = describe(data)
    assert told.kind.startswith("PKCS#12 bundle, protected by a password")
    assert told.binary is True and told.facts == () and told.expires is None


def test_a_pkcs12_bundle_without_a_password_is_read():
    cert, key = certificate()
    data = pkcs12.serialize_key_and_certificates(
        b"prod", key, cert, None, serialization.NoEncryption()
    )
    told = describe(data)
    assert told.kind == "PKCS#12 bundle, not protected by a password"
    assert dict(told.facts)["For"] == "api.example.com"


def test_a_pem_that_is_not_what_it_says_is_said_to_be_unreadable():
    broken = (
        b"-----BEGIN CERTIFICATE-----\nnot base64 at all!\n-----END CERTIFICATE-----\n"
    )
    told = describe(broken)
    assert told.kind == "PEM certificate — it cannot be read" and told.facts == ()


def test_another_pem_is_named_by_its_label():
    assert describe(
        b"-----BEGIN PUBLIC KEY-----\nAAAA\n-----END PUBLIC KEY-----\n"
    ).kind == ("PEM (public key)")


@pytest.mark.parametrize(
    ("data", "kind", "binary"),
    [
        (b"one line", "text, 1 line", False),
        (b"KEY=value\nOTHER=value\n", "text, 2 lines", False),
        (b"", "text, 0 lines", False),
        ("naïve ünïcode\n".encode(), "text, 1 line", False),
        (b"\x00\x01\x02\xff", "binary", True),
        (b"\xff\xfe not utf-8", "binary", True),
        (b"text with a \x00 in it", "binary", True),
        (b"\x30\x82 looks like a sequence and is not", "binary", True),
    ],
)
def test_anything_else_is_text_or_binary(data, kind, binary):
    told = describe(data)
    assert (told.kind, told.binary, told.size) == (kind, binary, len(data))


def test_what_is_told_is_plain_data():
    cert, _ = certificate()
    told = describe(pem(cert)).told()
    assert told["facts"] == [["For", "api.example.com"], ["Issued by", "Example CA"]]
    assert set(told) == {"kind", "size", "binary", "facts", "expires"}


def test_the_limit_is_databricks():
    assert LIMIT == 131072
