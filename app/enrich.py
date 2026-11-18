"""Click enrichment: user-agent parsing and referrer normalisation."""
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlsplit

from user_agents import parse as parse_ua


@dataclass(frozen=True)
class ClientInfo:
    browser: str
    os: str
    device: str


@lru_cache(maxsize=4096)
def parse_user_agent(user_agent: str | None) -> ClientInfo:
    """Parse a User-Agent string into browser, OS and device class (cached)."""
    if not user_agent:
        return ClientInfo("Unknown", "Unknown", "Unknown")
    ua = parse_ua(user_agent[:512])
    if ua.is_bot:
        device = "Bot"
    elif ua.is_mobile:
        device = "Mobile"
    elif ua.is_tablet:
        device = "Tablet"
    elif ua.is_pc:
        device = "Desktop"
    else:
        device = "Other"
    return ClientInfo(
        browser=ua.browser.family or "Unknown",
        os=ua.os.family or "Unknown",
        device=device,
    )


def referrer_host(referrer: str | None) -> str | None:
    """Only the host is kept: bounded cardinality and no query-string leakage."""
    if not referrer:
        return None
    try:
        host = urlsplit(referrer[:2048]).hostname
    except ValueError:
        return None
    return host.lower()[:255] if host else None
