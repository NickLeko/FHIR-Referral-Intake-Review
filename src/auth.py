"""SMART Backend Services: RS384 client assertions, in-memory token cache only."""

from __future__ import annotations

import math
import os
import re
import time
import uuid
from typing import Callable

from src.fhir_client import (
    FHIRClientError,
    FHIRConfigurationError,
    FHIRRetryLaterError,
    _close_response,
    _normalize_base_url,
)

READ_TYPES = (
    "Patient",
    "ServiceRequest",
    "Practitioner",
    "Condition",
    "Encounter",
    "Observation",
    "DocumentReference",
)
DEFAULT_SCOPES = " ".join([*(f"system/{t}.rs" for t in READ_TYPES), "system/Task.crs"])


class FHIRAuthError(FHIRClientError):
    """Auth failed; never continue anonymously or expose the token response."""


class SmartClientCredentials:
    def __init__(
        self,
        *,
        client_id: str,
        private_key: str,
        key_id: str,
        token_url: str,
        scopes: str,
        request: Callable,
        monotonic: Callable = time.monotonic,
        wall_clock: Callable = time.time,
    ):
        self.token_url = _normalize_base_url(token_url)
        if not self.token_url.startswith("https://"):
            raise FHIRConfigurationError("SMART token endpoint must use HTTPS.")
        if not all(
            isinstance(v, str) and v.strip()
            for v in (client_id, private_key, key_id, scopes)
        ):
            raise FHIRConfigurationError(
                "SMART client id, private key, key id and scopes are required."
            )
        if not set(scopes.split()) <= set(DEFAULT_SCOPES.split()):
            raise FHIRConfigurationError(
                "SMART scopes exceed the supported integration subset."
            )
        try:
            import jwt
            from cryptography.hazmat.primitives.serialization import (
                load_pem_private_key,
            )
            from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

            key = load_pem_private_key(private_key.encode(), password=None)
            if not isinstance(key, RSAPrivateKey) or key.key_size < 2048:
                raise ValueError("RSA key required")
        except (ImportError, ValueError, TypeError):
            raise FHIRConfigurationError(
                "SMART requires PyJWT[crypto] and a valid RSA private key (2048+ bits)."
            ) from None
        self._jwt = jwt
        self._key = key
        self._client_id = client_id
        self._key_id = key_id
        self.scopes = scopes
        self._request = request
        self._monotonic = monotonic
        self._wall_clock = wall_clock
        self._token = None
        self._expires_at = 0.0

    @classmethod
    def from_env(cls, *, request: Callable):
        mode = os.environ.get("FHIR_AUTH_MODE", "none")
        if mode == "none":
            if any(
                os.environ.get(k)
                for k in ("FHIR_CLIENT_ID", "FHIR_PRIVATE_KEY_PEM", "FHIR_TOKEN_URL")
            ):
                raise FHIRConfigurationError(
                    "Credentials are set: explicitly select FHIR_AUTH_MODE=smart."
                )
            return None
        if mode != "smart":
            raise FHIRConfigurationError("FHIR_AUTH_MODE must be none or smart.")
        required = (
            "FHIR_BASE_URL",
            "FHIR_CLIENT_ID",
            "FHIR_PRIVATE_KEY_PEM",
            "FHIR_KEY_ID",
            "FHIR_TOKEN_URL",
        )
        if not all(os.environ.get(k, "").strip() for k in required):
            raise FHIRConfigurationError(
                "SMART requires FHIR_BASE_URL, FHIR_CLIENT_ID, FHIR_PRIVATE_KEY_PEM, FHIR_KEY_ID and FHIR_TOKEN_URL."
            )
        return cls(
            client_id=os.environ["FHIR_CLIENT_ID"],
            private_key=os.environ["FHIR_PRIVATE_KEY_PEM"],
            key_id=os.environ["FHIR_KEY_ID"],
            token_url=os.environ["FHIR_TOKEN_URL"],
            scopes=os.environ.get("FHIR_SCOPES", DEFAULT_SCOPES),
            request=request,
        )

    def invalidate(self):
        self._token = None
        self._expires_at = 0.0

    def _assertion_form(self):
        now = int(self._wall_clock())
        assertion = self._jwt.encode(
            {
                "iss": self._client_id,
                "sub": self._client_id,
                "aud": self.token_url,
                "iat": now,
                "exp": now + 300,
                "jti": str(uuid.uuid4()),
            },
            self._key,
            algorithm="RS384",
            headers={"kid": self._key_id, "typ": "JWT"},
        )
        return {
            "grant_type": "client_credentials",
            "scope": self.scopes,
            "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
            "client_assertion": assertion,
        }

    def token(self):
        if self._token is not None and self._monotonic() < self._expires_at:
            return self._token
        self.invalidate()
        started = self._monotonic()
        # A new signed assertion (including jti) is generated on every retry.
        try:
            response, _ = self._request(
                "post",
                self.token_url,
                authenticated=False,
                headers={"Accept": "application/json"},
                data_factory=self._assertion_form,
            )
        except FHIRRetryLaterError:
            raise
        except FHIRClientError:
            raise FHIRAuthError(
                "SMART token acquisition failed; check configuration or retry after service recovery."
            ) from None
        try:
            data = response.json()
            token = data.get("access_token")
            expiry = data.get("expires_in")
            if (
                not isinstance(token, str)
                or not re.fullmatch(r"[A-Za-z0-9\-._~+/]+=*", token)
                or str(data.get("token_type", "")).lower() != "bearer"
                or isinstance(expiry, bool)
                or not isinstance(expiry, (int, float))
                or not math.isfinite(expiry)
                or expiry <= 0
            ):
                raise ValueError("invalid token response")
            granted = data.get("scope", self.scopes)
            if not isinstance(granted, str) or not set(self.scopes.split()) <= set(
                granted.split()
            ):
                raise ValueError("required scopes not granted")
            expires_at = started + expiry - min(30, expiry * 0.1)
            if expires_at <= self._monotonic():
                raise ValueError("token expired during acquisition")
        except (AttributeError, ValueError, TypeError):
            raise FHIRAuthError(
                "SMART token response is invalid or required scopes were not granted."
            ) from None
        finally:
            _close_response(response)
        self._token, self._expires_at = token, expires_at
        return token
