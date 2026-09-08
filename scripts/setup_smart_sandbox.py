"""Generate a local SMART Health IT test registration with signature checking enabled.

This writes ignored environment configuration only; it makes no network requests.
The launcher's /sim/ encoding is documented in docs/integration.md.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import shlex
import sys
import uuid

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from jwt.algorithms import RSAAlgorithm
from src.auth import DEFAULT_SCOPES


def sandbox_environment():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_id = str(uuid.uuid4())
    client_id = "referral-intake-" + str(uuid.uuid4())
    public = RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    public.update(kid=key_id, alg="RS384", use="sig")
    registration = [
        4,
        "",
        "",
        "",
        0,
        0,
        0,
        DEFAULT_SCOPES,
        "",
        client_id,
        "",
        "",
        "",
        json.dumps({"keys": [public]}, separators=(",", ":")),
        3,
        1,
        "",
    ]
    sim = (
        base64.urlsafe_b64encode(
            json.dumps(registration, separators=(",", ":")).encode()
        )
        .decode()
        .rstrip("=")
    )
    prefix = f"https://launch.smarthealthit.org/v/r4/sim/{sim}"
    return {
        "FHIR_AUTH_MODE": "smart",
        "FHIR_BASE_URL": prefix + "/fhir",
        "FHIR_TOKEN_URL": prefix + "/auth/token",
        "FHIR_CLIENT_ID": client_id,
        "FHIR_KEY_ID": key_id,
        "FHIR_SCOPES": DEFAULT_SCOPES,
        "FHIR_PRIVATE_KEY_PEM": key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode(),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".env.smart"))
    args = parser.parse_args(argv)
    config = sandbox_environment()
    # Exclusive create avoids accidentally rotating the identity/destination of queued reviews.
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as handle:
        for name, value in config.items():
            handle.write(f"export {name}={shlex.quote(value)}\n")
    print(
        f"Created {args.output}. Source this ignored file in your shell. Never commit it."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
