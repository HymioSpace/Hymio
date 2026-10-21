"""Issue a private-CA device certificate. Run on the operator machine, not in Hymio."""

import argparse
import datetime
import ipaddress
import os
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--host", required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
os.umask(0o077)
args.output.mkdir(mode=0o700, parents=True, exist_ok=True)
now = datetime.datetime.now(datetime.timezone.utc)
ca_path = args.output / "ca-key.pem"
if ca_path.exists():
    ca_key = serialization.load_pem_private_key(ca_path.read_bytes(), password=None)
    ca = x509.load_pem_x509_certificate((args.output / "ca.pem").read_bytes())
else:
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "Hymio device private CA")]
    )
    ca = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )
    ca_path.write_bytes(
        ca_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    (args.output / "ca.pem").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
try:
    san = x509.IPAddress(ipaddress.ip_address(args.host))
except ValueError:
    san = x509.DNSName(args.host)
leaf = (
    x509.CertificateBuilder()
    .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, args.host)]))
    .issuer_name(ca.subject)
    .public_key(key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now - datetime.timedelta(minutes=5))
    .not_valid_after(now + datetime.timedelta(days=90))
    .add_extension(x509.SubjectAlternativeName([san]), critical=False)
    .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
    .add_extension(
        x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False
    )
    .add_extension(
        x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
        critical=False,
    )
    .add_extension(
        x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
    )
    .sign(ca_key, hashes.SHA256())
)
(args.output / "server-key.pem").write_bytes(
    key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
)
(args.output / "server.pem").write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
print(
    "Device TLS certificate issued. Keep ca-key.pem offline; "
    "never copy it to Backend or the device."
)
