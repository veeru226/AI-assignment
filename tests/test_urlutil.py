import pytest

from app.errors import AppError
from app.urlutil import normalize_url, validate_alias


def norm(url, **kw):
    kw.setdefault("max_length", 2048)
    kw.setdefault("allow_private", False)
    return normalize_url(url, **kw)


def test_normalizes_case_default_port_and_empty_path():
    assert norm("HTTPS://Example.COM:443") == "https://example.com/"
    assert norm("http://example.com:8080/a?b=1#frag") == "http://example.com:8080/a?b=1#frag"


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "ftp://example.com",
        "javascript:alert(1)",
        "example.com",
        "http://",
        "http://user:pw@example.com",
        "http://exa mple.com",
        "http://localhost/x",
        "http://127.0.0.1/",
        "http://10.0.0.5/",
        "http://[::1]/",
        "http://169.254.169.254/latest/meta-data",
        "http://example.com:99999",
        "https://" + "a" * 2100 + ".com",
    ],
)
def test_rejects_unsafe_or_malformed(bad):
    with pytest.raises(AppError) as exc:
        norm(bad)
    assert exc.value.status_code == 422


def test_allow_private_flag():
    assert norm("http://localhost:3000/x", allow_private=True) == "http://localhost:3000/x"


def test_rejects_self_referencing_link():
    with pytest.raises(AppError):
        norm("https://sho.rt/abc", own_host="sho.rt")


@pytest.mark.parametrize("alias", ["my-link", "Promo_2030", "abc"])
def test_valid_alias(alias):
    assert validate_alias(alias) == alias


@pytest.mark.parametrize("alias", ["ab", "has space", "api", "DOCS", "abcDEF1", "x" * 33, "bad/slash"])
def test_invalid_alias(alias):
    with pytest.raises(AppError):
        validate_alias(alias)
