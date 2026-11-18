from app.cache import CachedLink, LRUCache
from app.enrich import parse_user_agent, referrer_host
from app.ratelimit import TokenBucketLimiter


def entry(i=1):
    """Build a CachedLink for id i pointing at https://e.com/i with no expiry."""
    return CachedLink(i, f"https://e.com/{i}", None)


def test_lru_evicts_least_recently_used():
    """A full LRU cache evicts the least recently used entry, keeping recently read ones."""
    c = LRUCache(2, 100)
    c.set("a", entry(1))
    c.set("b", entry(2))
    c.get("a")  # a is now most recent
    c.set("c", entry(3))
    assert c.get("b") is None
    assert c.get("a") and c.get("c")


def test_lru_ttl_expiry_and_delete():
    """LRU entries expire after their TTL and can be deleted explicitly."""
    t = [0.0]
    c = LRUCache(10, 5, monotonic=lambda: t[0])
    c.set("a", entry())
    t[0] = 4
    assert c.get("a")
    t[0] = 6
    assert c.get("a") is None
    c.set("b", entry())
    c.delete("b")
    assert c.get("b") is None


def test_token_bucket_burst_then_refill():
    """Token bucket allows the burst, then denies with retry_after, then refills; keys are separate."""
    t = [0.0]
    rl = TokenBucketLimiter(per_minute=60, burst=3, monotonic=lambda: t[0])
    assert [rl.check("k").allowed for _ in range(4)] == [True, True, True, False]
    denied = rl.check("k")
    assert not denied.allowed and 0 < denied.retry_after <= 1
    t[0] = 1.0  # 1 token/sec
    assert rl.check("k").allowed
    assert rl.check("other").allowed  # separate bucket


def test_token_bucket_bounds_memory():
    """The limiter keeps at most max_keys buckets."""
    rl = TokenBucketLimiter(60, 1, max_keys=10)
    for i in range(100):
        rl.check(f"k{i}")
    assert len(rl._buckets) == 10


def test_user_agent_parsing():
    """User-agent parsing detects browser, OS, and device for desktop, mobile, bot, and None."""
    chrome = parse_user_agent(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
    assert (chrome.browser, chrome.os, chrome.device) == ("Chrome", "Windows", "Desktop")
    iphone = parse_user_agent(
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    )
    assert iphone.device == "Mobile" and iphone.os == "iOS"
    assert parse_user_agent("Googlebot/2.1 (+http://www.google.com/bot.html)").device == "Bot"
    assert parse_user_agent(None).browser == "Unknown"


def test_referrer_host_strips_path_and_query():
    """referrer_host returns the lowercased host only, or None for missing/invalid referrers."""
    assert referrer_host("https://News.Example.com/a/b?token=secret") == "news.example.com"
    assert referrer_host(None) is None
    assert referrer_host("not a url") is None
