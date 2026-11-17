"""Validation and normalisation of user-supplied URLs and aliases."""
import hashlib
import ipaddress
import re
from urllib.parse import urlsplit, urlunsplit

from app.errors import AppError

ALIAS_RE = re.compile(r"^[A-Za-z0-9_-]{3,32}$")
# Generated codes are exactly 7 Base62 chars; forbidding that shape for custom
# aliases guarantees a vanity alias can never collide with a future generated code.
GENERATED_SHAPE_RE = re.compile(r"^[A-Za-z0-9]{7}$")
RESERVED_ALIASES = {"api", "docs", "redoc", "openapi", "healthz", "readyz", "admin", "static", "favicon"}
_DEFAULT_PORTS = {"http": 80, "https": 443}


def invalid_url(message: str) -> AppError:
    return AppError(422, "invalid_url", message)


def normalize_url(raw: str, *, max_length: int, allow_private: bool, own_host: str | None = None) -> str:
    raw = raw.strip()
    if not raw or len(raw) > max_length:
        raise invalid_url(f"URL must be 1-{max_length} characters")
    if any(ord(c) <= 32 or ord(c) == 127 for c in raw):
        raise invalid_url("URL must not contain whitespace or control characters")
    try:
        parts = urlsplit(raw)
        port = parts.port
    except ValueError:
        raise invalid_url("Malformed URL")

    scheme = parts.scheme.lower()
    if scheme not in _DEFAULT_PORTS:
        raise invalid_url("Only http and https URLs are allowed")
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        raise invalid_url("URL must include a host")
    if parts.username is not None or parts.password is not None:
        raise invalid_url("URLs with embedded credentials are not allowed")
    if own_host and host == own_host.lower():
        raise invalid_url("Shortening links that point back to this service is not allowed")
    if not allow_private and _is_private_host(host):
        raise invalid_url("URLs targeting localhost or private networks are not allowed")

    netloc = f"[{host}]" if ":" in host else host
    if port is not None and port != _DEFAULT_PORTS[scheme]:
        netloc = f"{netloc}:{port}"
    return urlunsplit((scheme, netloc, parts.path or "/", parts.query, parts.fragment))


def _is_private_host(host: str) -> bool:
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified


def url_hash(normalized_url: str) -> str:
    return hashlib.sha256(normalized_url.encode()).hexdigest()


def validate_alias(alias: str) -> str:
    if not ALIAS_RE.match(alias):
        raise AppError(422, "invalid_alias", "Alias must be 3-32 characters of letters, digits, '-' or '_'")
    if alias.lower() in RESERVED_ALIASES:
        raise AppError(422, "invalid_alias", "Alias is reserved")
    if GENERATED_SHAPE_RE.match(alias):
        raise AppError(
            422,
            "invalid_alias",
            "Exactly-7-character alphanumeric aliases are reserved for generated codes; add '-' or '_' or change the length",
        )
    return alias
