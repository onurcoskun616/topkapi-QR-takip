"""Generate a VAPID key pair for Web Push.

Run once, then copy the printed values into .env.prod and redeploy:

    python -m app.tools.vapid_keys

Prints the private and public PEM blocks as single lines (newlines escaped as
``\\n`` so they fit a .env value), plus the browser ``applicationServerKey``
for reference. The private key is a secret — treat it like AUTH_SECRET.
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def generate() -> dict[str, str]:
    private_key = ec.generate_private_key(ec.SECP256R1())

    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()

    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()

    raw_point = public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    application_server_key = base64.urlsafe_b64encode(raw_point).rstrip(b"=").decode()

    return {
        "private_pem": private_pem,
        "public_pem": public_pem,
        "application_server_key": application_server_key,
    }


def _as_env_line(pem: str) -> str:
    return pem.strip().replace("\n", "\\n")


if __name__ == "__main__":
    keys = generate()
    print("# --- .env.prod satırları (kopyalayın) ---")
    print(f'VAPID_PRIVATE_KEY="{_as_env_line(keys["private_pem"])}"')
    print(f'VAPID_PUBLIC_KEY="{_as_env_line(keys["public_pem"])}"')
    print('VAPID_SUBJECT="mailto:topkapiokullariai@gmail.com"')
    print()
    print("# Tarayıcı applicationServerKey (bilgi amaçlı, otomatik türetilir):")
    print(keys["application_server_key"])
