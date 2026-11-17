"""Country resolution. Order: trusted CDN/proxy header -> optional MaxMind GeoLite2 -> unknown."""
import logging
import re
from typing import Protocol

log = logging.getLogger(__name__)
_COUNTRY_RE = re.compile(r"^[A-Za-z]{2}$")


class GeoResolver(Protocol):
    def country(self, ip: str | None, header_hint: str | None) -> str | None: ...


class NullGeoResolver:
    def country(self, ip, header_hint):
        return _clean(header_hint)


class MaxMindGeoResolver:
    def __init__(self, db_path: str):
        import geoip2.database  # optional dependency

        self._reader = geoip2.database.Reader(db_path)

    def country(self, ip, header_hint):
        hinted = _clean(header_hint)
        if hinted or not ip:
            return hinted
        try:
            return _clean(self._reader.country(ip).country.iso_code)
        except Exception:  # address not in DB, private IP, malformed...
            return None


def _clean(value: str | None) -> str | None:
    if value and _COUNTRY_RE.match(value.strip()) and value.strip().upper() not in {"XX", "T1"}:
        return value.strip().upper()
    return None


def build_geo_resolver(db_path: str) -> GeoResolver:
    if db_path:
        try:
            return MaxMindGeoResolver(db_path)
        except Exception as exc:
            log.warning("GeoIP database unavailable (%s); falling back to header-only country", exc)
    return NullGeoResolver()
