"""
JWS Key Generation for Bilateral Logger Signatures

Generates RSA keypair for signing audit records.
- Private key: config/private_key.pem (gitignored, secret)
- Public key: config/public_key.pem (committed to repo, for verification)

Run once at project setup, or on first import if keys don't exist.
"""

import pathlib
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend


def generate_keypair(key_dir: pathlib.Path, key_size: int = 2048) -> tuple:
    """
    Generate RSA keypair and save to PEM files.

    Args:
        key_dir: Directory to save keys (typically: config/)
        key_size: RSA key size in bits (2048 for MVP, 4096 for production)

    Returns:
        (private_key_path, public_key_path)
    """
    key_dir = pathlib.Path(key_dir)
    key_dir.mkdir(parents=True, exist_ok=True)

    private_key_path = key_dir / "private_key.pem"
    public_key_path = key_dir / "public_key.pem"

    # Check if keys already exist
    if private_key_path.exists() and public_key_path.exists():
        print(f"✓ Keys already exist at {key_dir}")
        return private_key_path, public_key_path

    print(f"Generating {key_size}-bit RSA keypair...")

    # Generate private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_size,
        backend=default_backend()
    )

    # Serialize private key to PEM (unencrypted, for operational simplicity)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

    # Serialize public key to PEM
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    # Write to files
    with private_key_path.open('wb') as f:
        f.write(private_pem)
    private_key_path.chmod(0o600)  # Restrict to owner only

    with public_key_path.open('wb') as f:
        f.write(public_pem)

    print(f"✓ Private key saved to {private_key_path} (mode 0o600)")
    print(f"✓ Public key saved to {public_key_path}")

    return private_key_path, public_key_path


def ensure_keys_exist(key_dir: pathlib.Path = None) -> tuple:
    """
    Ensure keypair exists, generating if necessary.

    Args:
        key_dir: Directory for keys (defaults to {repo_root}/config)

    Returns:
        (private_key_path, public_key_path)
    """
    if key_dir is None:
        key_dir = pathlib.Path(__file__).parent

    return generate_keypair(key_dir)


if __name__ == "__main__":
    import sys
    key_dir = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(__file__).parent
    private_path, public_path = generate_keypair(key_dir)
    print(f"\nKeys ready. Use {public_path} for verification.")
