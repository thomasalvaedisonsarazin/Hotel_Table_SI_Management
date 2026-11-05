"""Creates the key that signs the Android app. Phones only accept updates signed with the same key,
so keep the two output files somewhere safe and out of this repo.

Run once: backend/.venv/Scripts/python deploy/make_android_key.py <folder outside the repo>
"""

import base64
import datetime
import secrets
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12


def main() -> None:
    folder = Path(sys.argv[1]).resolve()
    if Path(__file__).resolve().parent.parent in [folder, *folder.parents]:
        sys.exit("Choose a folder outside the repo, so the key can't be committed by accident.")
    folder.mkdir(parents=True, exist_ok=True)
    key_file = folder / "dineops-android-key.b64.txt"
    if key_file.exists():
        sys.exit(f"{key_file} already exists. Replacing it would stop phones taking updates.")

    password = secrets.token_urlsafe(24)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "DineOps SI")])
    now = datetime.datetime.now(datetime.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=365 * 30))
        .sign(key, hashes.SHA256())
    )
    keystore = pkcs12.serialize_key_and_certificates(
        b"dineops",
        key,
        certificate,
        None,
        serialization.BestAvailableEncryption(password.encode()),
    )
    key_file.write_text(base64.b64encode(keystore).decode())
    (folder / "dineops-android-key-password.txt").write_text(password)
    sys.stdout.write(f"Saved to {folder}. Add both files' contents as GitHub secrets (see README).\n")


if __name__ == "__main__":
    main()
