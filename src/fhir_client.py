from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Collection
from urllib.parse import urlencode, urlsplit

import requests

from src.models import ResourceProvenance


DEFAULT_FHIR_BASE_URL = "https://hapi.fhir.org/baseR4"
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_BACKOFF_SECONDS = 0.25
DEFAULT_MAX_RETRY_DELAY_SECONDS = 5.0
DEFAULT_USER_AGENT = "FHIR-Referral-Intake-Review/1.0"
FHIR_JSON_MEDIA_TYPE = "application/fhir+json"

_MAX_CONFIGURED_RETRIES = 10
_MAX_TIMEOUT_SECONDS = 120.0
_FHIR_ID_RE = re.compile(r"^[A-Za-z0-9.-]{1,64}$")
_FHIR_RESOURCE_TYPE_RE = re.compile(r"^[A-Z][A-Za-z0-9]{0,254}$")
_FHIR_REFERENCE_RE = re.compile(
    r"^(?P<resource_type>[A-Z][A-Za-z0-9]{0,254})/"
    r"(?P<resource_id>[A-Za-z0-9.-]{1,64})"
    r"(?:/_history/(?P<version_id>[A-Za-z0-9.-]{1,64}))?$"
)


class FHIRClientError(Exception):
    """Base class for safe, caller-facing FHIR integration failures."""


class FHIRConfigurationError(FHIRClientError):
    """The client was configured with an unsafe or unusable value."""


class FHIRReferenceError(FHIRClientError):
    """A FHIR reference is malformed, outside the configured server, or disallowed."""


class FHIRTransportError(FHIRClientError):
    """The configured FHIR server could not be reached after bounded retries."""

    def __init__(self, request_url: str, attempts: int) -> None:
        self.request_url = request_url
        self.attempts = attempts
        super().__init__(f"FHIR request failed after {attempts} transport attempt(s).")


class FHIRHTTPError(FHIRClientError):
    """The FHIR server returned a non-success HTTP status."""

    def __init__(self, status_code: int, request_url: str, attempts: int) -> None:
        self.status_code = status_code
        self.request_url = request_url
        self.attempts = attempts
        super().__init__(f"FHIR server returned HTTP {status_code} for a request.")


class FHIRNotFoundError(FHIRHTTPError):
    """The requested resource does not exist on the configured FHIR server."""


class FHIRResponseError(FHIRClientError):
    """A successful HTTP response was not a valid response to the requested read."""

    def __init__(self, request_url: str, problem: str) -> None:
        self.request_url = request_url
        self.problem = problem
        super().__init__(f"FHIR server returned an invalid read response: {problem}.")


class FHIRRetryLaterError(FHIRHTTPError):
    """The server requested a delay beyond the synchronous retry budget."""

    def __init__(self, status_code, request_url, attempts, retry_after):
        super().__init__(status_code, request_url, attempts)
        self.retry_after = retry_after
        self.args = (
            f"FHIR HTTP {status_code}: retry deferred for {retry_after:.1f} seconds.",
        )


@dataclass(frozen=True)
class FetchedResource:
    resource: dict[str, Any]
    provenance: ResourceProvenance
    request_url: str


class FHIRClient:
    """A bounded FHIR R4 transport with optional SMART backend-service authentication."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff: float = DEFAULT_RETRY_BACKOFF_SECONDS,
        max_retry_delay: float = DEFAULT_MAX_RETRY_DELAY_SECONDS,
        user_agent: str = DEFAULT_USER_AGENT,
        session: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime | str] | None = None,
        token_provider: Any = None,
    ) -> None:
        configured_base_url = (
            os.environ.get("FHIR_BASE_URL", DEFAULT_FHIR_BASE_URL)
            if base_url is None
            else base_url
        )
        self.base_url = _normalize_base_url(configured_base_url)
        self.timeout = _validate_positive_number(
            timeout,
            name="timeout",
            maximum=_MAX_TIMEOUT_SECONDS,
        )
        self.max_retries = _validate_retry_count(max_retries)
        self.retry_backoff = _validate_nonnegative_number(
            retry_backoff,
            name="retry_backoff",
        )
        self.max_retry_delay = _validate_positive_number(
            max_retry_delay,
            name="max_retry_delay",
            maximum=_MAX_TIMEOUT_SECONDS,
        )
        if not isinstance(user_agent, str) or not user_agent.strip():
            raise FHIRConfigurationError("user_agent must be a non-empty string.")
        if "\r" in user_agent or "\n" in user_agent:
            raise FHIRConfigurationError("user_agent contains an invalid character.")
        if not callable(sleep):
            raise FHIRConfigurationError("sleep must be callable.")
        if clock is not None and not callable(clock):
            raise FHIRConfigurationError("clock must be callable.")

        self.user_agent = user_agent
        self._session = session if session is not None else requests.Session()
        self._sleep = sleep
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._base_parts = urlsplit(self.base_url)
        self._base_origin = _origin(self._base_parts)
        self._base_path = self._base_parts.path.rstrip("/")
        self._retry_not_before = 0.0
        self._token_provider = token_provider
        if token_provider is None:
            from src.auth import SmartClientCredentials

            self._token_provider = SmartClientCredentials.from_env(
                request=self._request_with_retries
            )
            if self._token_provider and self.base_url != _normalize_base_url(
                os.environ["FHIR_BASE_URL"]
            ):
                raise FHIRConfigurationError(
                    "SMART credentials are bound to FHIR_BASE_URL; configure the destination explicitly in the environment."
                )
        if self._token_provider and self._base_parts.scheme != "https":
            raise FHIRConfigurationError("Authenticated FHIR access requires HTTPS.")

    def get_resource(
        self,
        resource_type: str,
        resource_id: str,
        *,
        version_id: str | None = None,
    ) -> FetchedResource:
        """Fetch and validate one resource, optionally at a specific history version."""

        validated_type = _validate_resource_type(resource_type)
        validated_id = _validate_fhir_id(resource_id, name="resource_id")
        validated_version = (
            _validate_fhir_id(version_id, name="version_id")
            if version_id is not None
            else None
        )
        request_url = f"{self.base_url}/{validated_type}/{validated_id}"
        if validated_version is not None:
            request_url = f"{request_url}/_history/{validated_version}"

        response, attempts = self._get_with_retries(request_url)
        try:
            resource = self._validated_json_resource(
                response,
                request_url=request_url,
                expected_type=validated_type,
                expected_id=validated_id,
            )
        finally:
            _close_response(response)

        meta = resource.get("meta")
        version = _validated_optional_fhir_id(meta, "versionId")
        last_updated = _validated_optional_instant(meta, "lastUpdated")
        fetched_at = _format_fetched_at(self._clock())
        provenance = ResourceProvenance(
            server_base_url=self.base_url,
            resource_type=validated_type,
            resource_id=validated_id,
            version_id=version,
            last_updated=last_updated,
            fetched_at=fetched_at,
        )
        return FetchedResource(
            resource=resource,
            provenance=provenance,
            request_url=request_url,
        )

    def get_reference(
        self,
        reference: str,
        expected_types: Collection[str] | str,
    ) -> FetchedResource:
        """Resolve a safe local-server relative or absolute FHIR reference."""

        allowed_types = _validate_expected_types(expected_types)
        relative_reference = self._local_relative_reference(reference)
        match = _FHIR_REFERENCE_RE.fullmatch(relative_reference)
        if match is None:
            raise FHIRReferenceError("FHIR reference has an unsupported shape.")

        resource_type = match.group("resource_type")
        if resource_type not in allowed_types:
            raise FHIRReferenceError(
                "FHIR reference resource type is not allowed in this context."
            )
        return self.get_resource(
            resource_type,
            match.group("resource_id"),
            version_id=match.group("version_id"),
        )

    def get_search_bundle(
        self,
        resource_type: str,
        *,
        count: int = 20,
        page_url: str | None = None,
    ) -> dict[str, Any]:
        """Fetch one search page without following links outside this FHIR base."""

        validated_type = _validate_resource_type(resource_type)
        if page_url is None:
            if (
                isinstance(count, bool)
                or not isinstance(count, int)
                or not 1 <= count <= 50
            ):
                raise FHIRConfigurationError("search count must be between 1 and 50.")
            request_url = (
                f"{self.base_url}/{validated_type}?{urlencode({'_count': count})}"
            )
        else:
            request_url = self._validated_page_url(page_url, validated_type)

        response, _ = self._get_with_retries(request_url)
        try:
            try:
                payload = response.json()
            except (ValueError, TypeError) as exc:
                raise FHIRResponseError(
                    request_url,
                    "search response body is not valid JSON",
                ) from exc
            self._validate_search_bundle(payload, request_url, validated_type)
            return payload
        finally:
            _close_response(response)

    def _validated_page_url(self, page_url: str, resource_type: str) -> str:
        if (
            not isinstance(page_url, str)
            or not page_url
            or page_url != page_url.strip()
        ):
            raise FHIRReferenceError("Search next link must be a non-empty URL.")
        if "\\" in page_url:
            raise FHIRReferenceError("Search next link has an unsupported shape.")
        try:
            parts = urlsplit(page_url)
        except ValueError as exc:
            raise FHIRReferenceError("Search next link is not a valid URL.") from exc
        if not parts.scheme or not parts.netloc or parts.fragment:
            raise FHIRReferenceError("Search next link must be an absolute URL.")
        if parts.username is not None or parts.password is not None:
            raise FHIRReferenceError("Search next link origin is not allowed.")
        try:
            page_origin = _origin(parts)
        except (FHIRConfigurationError, ValueError) as exc:
            raise FHIRReferenceError("Search next link origin is not allowed.") from exc
        if page_origin != self._base_origin:
            raise FHIRReferenceError("Search next link origin is not allowed.")
        if "%" in parts.path or any(
            segment in {".", ".."} for segment in parts.path.split("/")
        ):
            raise FHIRReferenceError("Search next link has an unsafe path.")
        if self._base_path and not (
            parts.path == self._base_path
            or parts.path == f"{self._base_path}/{resource_type}"
        ):
            raise FHIRReferenceError(
                "Search next link is outside the configured base path."
            )
        if not self._base_path and parts.path not in {"/", f"/{resource_type}"}:
            raise FHIRReferenceError(
                "Search next link is outside the configured base path."
            )
        return page_url

    def _local_relative_reference(self, reference: str) -> str:
        if not isinstance(reference, str) or not reference:
            raise FHIRReferenceError("FHIR reference must be a non-empty string.")
        if reference != reference.strip() or "\\" in reference:
            raise FHIRReferenceError("FHIR reference has an unsupported shape.")
        if reference.startswith("#"):
            raise FHIRReferenceError(
                "Contained references must be resolved from the containing resource."
            )

        try:
            parts = urlsplit(reference)
        except ValueError as exc:
            raise FHIRReferenceError("FHIR reference is not a valid URL.") from exc

        if not parts.scheme and not parts.netloc:
            if parts.query or parts.fragment or reference.startswith("/"):
                raise FHIRReferenceError("FHIR reference has an unsupported shape.")
            return parts.path

        if not parts.scheme or not parts.netloc:
            raise FHIRReferenceError("FHIR reference has an unsupported shape.")
        if parts.username is not None or parts.password is not None:
            raise FHIRReferenceError("FHIR reference origin is not allowed.")
        if parts.query or parts.fragment:
            raise FHIRReferenceError("FHIR reference has an unsupported shape.")
        try:
            reference_origin = _origin(parts)
        except (FHIRConfigurationError, ValueError) as exc:
            raise FHIRReferenceError("FHIR reference origin is not allowed.") from exc
        if reference_origin != self._base_origin:
            raise FHIRReferenceError("FHIR reference origin is not allowed.")

        if self._base_path:
            required_prefix = f"{self._base_path}/"
            if not parts.path.startswith(required_prefix):
                raise FHIRReferenceError(
                    "FHIR reference is outside the configured base path."
                )
            return parts.path[len(required_prefix) :]
        if not parts.path.startswith("/"):
            raise FHIRReferenceError("FHIR reference has an unsupported shape.")
        return parts.path[1:]

    def _get_with_retries(self, request_url: str) -> tuple[Any, int]:
        return self._request_with_retries("get", request_url)

    def _request_with_retries(
        self,
        method,
        request_url,
        *,
        headers=None,
        authenticated=True,
        data_factory=None,
        **kwargs,
    ):
        """Retries only safe reads, OAuth grants, or conditional creates supplied by callers."""
        remaining_delay = self._retry_not_before - time.monotonic()
        if remaining_delay > 0:
            raise FHIRRetryLaterError(429, request_url, 0, remaining_delay)
        base_headers = {
            "Accept": FHIR_JSON_MEDIA_TYPE,
            "User-Agent": self.user_agent,
            **(headers or {}),
        }
        transient_failures = 0
        auth_retried = False
        attempts = 0
        while True:
            attempts += 1
            request_headers = dict(base_headers)
            if authenticated and self._token_provider:
                request_headers["Authorization"] = (
                    f"Bearer {self._token_provider.token()}"
                )
            request_kwargs = dict(kwargs)
            if data_factory is not None:
                request_kwargs["data"] = data_factory()
            try:
                response = getattr(self._session, method)(
                    request_url,
                    headers=request_headers,
                    timeout=self.timeout,
                    allow_redirects=False,
                    **request_kwargs,
                )
            except requests.RequestException:
                if transient_failures >= self.max_retries:
                    raise FHIRTransportError(request_url, attempts) from None
                transient_failures += 1
                self._sleep(self._retry_delay(transient_failures, None))
                continue
            status_code = getattr(response, "status_code", None)
            if not isinstance(status_code, int):
                _close_response(response)
                raise FHIRResponseError(request_url, "missing HTTP status")
            if 200 <= status_code < 300:
                return response, attempts
            if (
                status_code == 401
                and authenticated
                and self._token_provider
                and not auth_retried
            ):
                _close_response(response)
                self._token_provider.invalidate()
                auth_retried = True
                continue
            if status_code == 429 or 500 <= status_code < 600:
                retry_after = _retry_after_seconds(
                    getattr(response, "headers", None), now=self._clock
                )
                if retry_after is not None and retry_after > self.max_retry_delay:
                    _close_response(response)
                    self._retry_not_before = time.monotonic() + retry_after
                    raise FHIRRetryLaterError(
                        status_code, request_url, attempts, retry_after
                    )
                if status_code == 429 and transient_failures >= self.max_retries:
                    _close_response(response)
                    delay = self._retry_delay(transient_failures + 1, retry_after)
                    self._retry_not_before = time.monotonic() + delay
                    raise FHIRRetryLaterError(status_code, request_url, attempts, delay)
                if transient_failures < self.max_retries:
                    _close_response(response)
                    transient_failures += 1
                    self._sleep(self._retry_delay(transient_failures, retry_after))
                    continue
            _close_response(response)
            error_type = FHIRNotFoundError if status_code == 404 else FHIRHTTPError
            raise error_type(status_code, request_url, attempts)

    def check_task_write_capability(self):
        url = f"{self.base_url}/metadata"
        response, _ = self._get_with_retries(url)
        try:
            payload = response.json()
            if (
                not isinstance(payload, dict)
                or payload.get("resourceType") != "CapabilityStatement"
            ):
                raise ValueError()
            for rest in payload.get("rest", []):
                if rest.get("mode") != "server":
                    continue
                for resource in rest.get("resource", []):
                    if (
                        resource.get("type") == "Task"
                        and resource.get("conditionalCreate") is True
                        and {"create", "search-type"}
                        <= {i.get("code") for i in resource.get("interaction", [])}
                        and any(
                            p.get("name") == "identifier"
                            for p in resource.get("searchParam", [])
                        )
                    ):
                        return
        except (ValueError, TypeError, AttributeError):
            raise FHIRResponseError(url, "invalid CapabilityStatement") from None
        finally:
            _close_response(response)
        raise FHIRConfigurationError(
            "Server must advertise Task conditional create and identifier search; write-back is disabled."
        )

    def conditional_create_task(self, task, identifier):
        response, _ = self._request_with_retries(
            "post",
            f"{self.base_url}/Task",
            json=task,
            headers={
                "Content-Type": FHIR_JSON_MEDIA_TYPE,
                "Prefer": "return=representation",
                "If-None-Exist": urlencode({"identifier": identifier}),
            },
        )
        # Even a 2xx is verified by identifier search; no body or Location is trusted.
        _close_response(response)

    def find_tasks(self, identifier):
        url = (
            f"{self.base_url}/Task?{urlencode({'identifier': identifier, '_count': 2})}"
        )
        response, _ = self._get_with_retries(url)
        try:
            payload = response.json()
            self._validate_search_bundle(payload, url, "Task")
            return payload
        except (ValueError, TypeError):
            raise FHIRResponseError(url, "invalid Task search JSON") from None
        finally:
            _close_response(response)

    @staticmethod
    def _validate_search_bundle(payload, request_url, expected_type):
        if (
            not isinstance(payload, dict)
            or payload.get("resourceType") != "Bundle"
            or payload.get("type") != "searchset"
        ):
            raise FHIRResponseError(request_url, "expected a searchset Bundle")
        for field in ("entry", "link"):
            if field in payload and not isinstance(payload[field], list):
                raise FHIRResponseError(
                    request_url, f"search Bundle {field} is not a list"
                )
        for entry in payload.get("entry", []):
            resource = entry.get("resource") if isinstance(entry, dict) else None
            if not isinstance(resource, dict) or not isinstance(
                resource.get("resourceType"), str
            ):
                raise FHIRResponseError(
                    request_url, "search entry must contain a resource"
                )
            if resource["resourceType"] != expected_type:
                raise FHIRResponseError(request_url, "unexpected search resource type")
            if not isinstance(resource.get("id"), str) or not _FHIR_ID_RE.fullmatch(
                resource["id"]
            ):
                raise FHIRResponseError(request_url, "invalid search resource id")
            search = entry.get("search", {})
            if not isinstance(search, dict) or search.get("mode", "match") != "match":
                raise FHIRResponseError(request_url, "expected matching search entries")
        for link in payload.get("link", []):
            if (
                not isinstance(link, dict)
                or not isinstance(link.get("relation"), str)
                or not isinstance(link.get("url"), str)
            ):
                raise FHIRResponseError(request_url, "invalid search link")

    def _retry_delay(self, attempt: int, retry_after: float | None) -> float:
        exponential_delay = self.retry_backoff * (2 ** (attempt - 1))
        requested_delay = max(exponential_delay, retry_after or 0.0)
        return min(requested_delay, self.max_retry_delay)

    @staticmethod
    def _validated_json_resource(
        response: Any,
        *,
        request_url: str,
        expected_type: str,
        expected_id: str,
    ) -> dict[str, Any]:
        try:
            payload = response.json()
        except (ValueError, TypeError) as exc:
            raise FHIRResponseError(
                request_url, "response body is not valid JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise FHIRResponseError(request_url, "JSON top level is not an object")

        actual_type = payload.get("resourceType")
        if not isinstance(actual_type, str) or not _FHIR_RESOURCE_TYPE_RE.fullmatch(
            actual_type
        ):
            raise FHIRResponseError(request_url, "resourceType is missing or invalid")
        if actual_type != expected_type:
            raise FHIRResponseError(
                request_url, "resourceType does not match the request"
            )

        actual_id = payload.get("id")
        if not isinstance(actual_id, str) or not _FHIR_ID_RE.fullmatch(actual_id):
            raise FHIRResponseError(request_url, "resource id is missing or invalid")
        if actual_id != expected_id:
            raise FHIRResponseError(
                request_url, "resource id does not match the request"
            )
        return payload


def _normalize_base_url(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FHIRConfigurationError("FHIR base URL must be a non-empty string.")
    if value != value.strip() or "\\" in value:
        raise FHIRConfigurationError("FHIR base URL has an unsupported shape.")
    try:
        parts = urlsplit(value)
    except ValueError as exc:
        raise FHIRConfigurationError("FHIR base URL is not a valid URL.") from exc
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        raise FHIRConfigurationError("FHIR base URL must use HTTP or HTTPS.")
    if parts.username is not None or parts.password is not None:
        raise FHIRConfigurationError("FHIR base URL must not include credentials.")
    if parts.query or parts.fragment:
        raise FHIRConfigurationError(
            "FHIR base URL must not include query or fragment."
        )
    if (
        "%" in parts.path
        or "//" in parts.path
        or any(segment in {".", ".."} for segment in parts.path.split("/"))
    ):
        raise FHIRConfigurationError("FHIR base URL has an unsafe path.")
    try:
        _origin(parts)
    except ValueError as exc:
        raise FHIRConfigurationError("FHIR base URL has an invalid port.") from exc
    return value.rstrip("/")


def _origin(parts: Any) -> tuple[str, str, int]:
    scheme = parts.scheme.lower()
    hostname = parts.hostname
    if hostname is None:
        raise FHIRConfigurationError("URL origin is missing a hostname.")
    port = parts.port
    if port is None:
        port = 443 if scheme == "https" else 80
    return scheme, hostname.lower(), port


def _validate_resource_type(value: Any) -> str:
    if not isinstance(value, str) or not _FHIR_RESOURCE_TYPE_RE.fullmatch(value):
        raise FHIRReferenceError("FHIR resource type is invalid.")
    return value


def _validate_fhir_id(value: Any, *, name: str) -> str:
    if not isinstance(value, str) or not _FHIR_ID_RE.fullmatch(value):
        raise FHIRReferenceError(f"FHIR {name} is invalid.")
    return value


def _validate_expected_types(values: Collection[str] | str) -> frozenset[str]:
    if isinstance(values, str):
        candidates = [values]
    else:
        try:
            candidates = list(values)
        except TypeError as exc:
            raise FHIRReferenceError(
                "expected_types must be a non-empty collection."
            ) from exc
    if not candidates:
        raise FHIRReferenceError("expected_types must be a non-empty collection.")
    return frozenset(_validate_resource_type(value) for value in candidates)


def _validate_retry_count(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise FHIRConfigurationError("max_retries must be an integer.")
    if value < 0 or value > _MAX_CONFIGURED_RETRIES:
        raise FHIRConfigurationError(
            f"max_retries must be between 0 and {_MAX_CONFIGURED_RETRIES}."
        )
    return value


def _validate_positive_number(value: Any, *, name: str, maximum: float) -> float:
    number = _validate_nonnegative_number(value, name=name)
    if number == 0 or number > maximum:
        raise FHIRConfigurationError(f"{name} must be greater than 0 and bounded.")
    return number


def _validate_nonnegative_number(value: Any, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FHIRConfigurationError(f"{name} must be a number.")
    number = float(value)
    if number < 0 or number == float("inf") or number != number:
        raise FHIRConfigurationError(f"{name} must be a finite non-negative number.")
    return number


def _validated_optional_fhir_id(meta: Any, key: str) -> str | None:
    if not isinstance(meta, dict):
        return None
    value = meta.get(key)
    if isinstance(value, str) and _FHIR_ID_RE.fullmatch(value):
        return value
    return None


def _validated_optional_instant(meta: Any, key: str) -> str | None:
    if not isinstance(meta, dict):
        return None
    value = meta.get(key)
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return value


def _format_fetched_at(value: datetime | str) -> str:
    if isinstance(value, str):
        if not value:
            raise FHIRConfigurationError("clock returned an empty timestamp.")
        return value
    if not isinstance(value, datetime):
        raise FHIRConfigurationError("clock must return a datetime or ISO string.")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _retry_after_seconds(
    headers: Any,
    *,
    now: Callable[[], datetime | str],
) -> float | None:
    if not hasattr(headers, "get"):
        return None
    raw_value = headers.get("Retry-After")
    if not isinstance(raw_value, str):
        return None
    try:
        seconds = float(raw_value)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(raw_value)
            current = now()
            if not isinstance(current, datetime):
                return None
            if current.tzinfo is None:
                current = current.replace(tzinfo=timezone.utc)
            seconds = (retry_at - current.astimezone(retry_at.tzinfo)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return None
    if seconds < 0 or seconds == float("inf") or seconds != seconds:
        return None
    return seconds


def _close_response(response: Any) -> None:
    close = getattr(response, "close", None)
    if callable(close):
        close()
