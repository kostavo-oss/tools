"""What a file is, before it becomes a secret.

Somebody who picks a certificate wants to know it is the right one before it
goes in: what kind of file, who it is for, who issued it, when it expires. This
reads that out of the bytes and nothing else — no I/O, no clock, no workspace.

Parsing is `cryptography`'s; what cannot be read is said to be what it looks
like, never guessed at.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives.serialization import pkcs12

#: The most a Databricks secret may hold.
#: https://docs.databricks.com/api/workspace/secrets/putsecret
LIMIT = 128 * 1024

_PEM = re.compile(r"-----BEGIN ([A-Z0-9 ]+)-----")
# the first thing in a PKCS#12 file, once past its lengths: "this holds data"
_PKCS7_DATA = bytes.fromhex("2a864886f70d010701")


@dataclass(frozen=True)
class Described:
    kind: str
    size: int
    #: Whether it is no text: stored byte for byte, shown as what it is.
    binary: bool = False
    #: A certificate's facts, in the order they are shown.
    facts: tuple[tuple[str, str], ...] = field(default=())
    #: When a certificate in it expires, as an ISO date and time in UTC.
    expires: str | None = None

    def told(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "size": self.size,
            "binary": self.binary,
            "facts": [list(fact) for fact in self.facts],
            "expires": self.expires,
        }


def describe(data: bytes) -> Described:
    size = len(data)
    text = _text(data)
    if text is not None:
        labels = _PEM.findall(text)
        if labels:
            return _pem(data, labels, size)
    for read in (_der, _pkcs12):
        found = read(data, size)
        if found:
            return found
    if text is not None:
        lines = text.count("\n") + (0 if text.endswith("\n") or not text else 1)
        return Described(f"text, {lines} line{'' if lines == 1 else 's'}", size)
    return Described("binary", size, binary=True)


def _text(data: bytes) -> str | None:
    """The bytes as text, when they are text: UTF-8 with nothing unprintable."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if any(ord(c) < 32 and c not in "\t\n\r" for c in text):
        return None
    return text


def _pem(data: bytes, labels: list[str], size: int) -> Described:
    certificates = labels.count("CERTIFICATE")
    keys = [label for label in labels if label.endswith("PRIVATE KEY")]
    if certificates and keys:
        kind = "PEM certificate with its private key"
    elif certificates > 1:
        kind = f"PEM certificate chain ({certificates})"
    elif certificates:
        kind = "PEM certificate"
    elif keys:
        locked = any(label.startswith("ENCRYPTED") for label in keys)
        kind = "PEM private key" + (", encrypted" if locked else "")
    else:
        kind = f"PEM ({labels[0].lower()})"
    if not certificates:
        return Described(kind, size)
    try:
        first = x509.load_pem_x509_certificates(data)[0]
    except (ValueError, IndexError):
        return Described(f"{kind} — it cannot be read", size)
    return Described(kind, size, facts=_facts(first), expires=_expires(first))


def _der(data: bytes, size: int) -> Described | None:
    try:
        certificate = x509.load_der_x509_certificate(data)
    except ValueError:
        return None
    return Described(
        "DER certificate",
        size,
        binary=True,
        facts=_facts(certificate),
        expires=_expires(certificate),
    )


def _pkcs12(data: bytes, size: int) -> Described | None:
    if not (data[:1] == b"\x30" and _PKCS7_DATA in data[:64]):
        return None
    try:
        bundle = pkcs12.load_pkcs12(data, None)
    except ValueError:
        # the right shape, and it will not open without its password
        return Described(
            "PKCS#12 bundle, protected by a password — its contents are not read",
            size,
            binary=True,
        )
    certificate = bundle.cert.certificate if bundle.cert else None
    if certificate is None:
        return Described("PKCS#12 bundle", size, binary=True)
    return Described(
        "PKCS#12 bundle, not protected by a password",
        size,
        binary=True,
        facts=_facts(certificate),
        expires=_expires(certificate),
    )


def _facts(certificate: x509.Certificate) -> tuple[tuple[str, str], ...]:
    return (("For", _for(certificate)), ("Issued by", _name(certificate.issuer)))


def _expires(certificate: x509.Certificate) -> str:
    return certificate.not_valid_after_utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def _for(certificate: x509.Certificate) -> str:
    """The names a certificate is for: those it lists, or failing that its subject."""
    try:
        listed = certificate.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value.get_values_for_type(x509.DNSName)
    except x509.ExtensionNotFound:
        listed = []
    if not listed:
        return _name(certificate.subject)
    shown = ", ".join(listed[:3])
    return shown if len(listed) <= 3 else f"{shown} and {len(listed) - 3} more"


def _name(name: x509.Name) -> str:
    """A name as people say it: the common name, else the organisation, else all of it."""
    for oid in (x509.NameOID.COMMON_NAME, x509.NameOID.ORGANIZATION_NAME):
        found = name.get_attributes_for_oid(oid)
        if found:
            return str(found[0].value)
    return name.rfc4514_string() or "(no name)"
