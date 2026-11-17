import pytest

from app.codegen import MAX_ID, CodeGenerator, base62_decode, base62_encode


def test_base62_roundtrip():
    for n in (0, 1, 61, 62, 12345678901):
        assert base62_decode(base62_encode(n, width=1)) == n


def test_base62_rejects_invalid_chars():
    with pytest.raises(ValueError):
        base62_decode("ab$")


def test_codes_are_fixed_length_and_roundtrip():
    gen = CodeGenerator("secret")
    for link_id in (1, 2, 999, 1_000_000, MAX_ID):
        code = gen.encode(link_id)
        assert len(code) == 7 and code.isalnum()
        assert gen.decode(code) == link_id


def test_no_collisions_over_sequential_ids():
    gen = CodeGenerator("secret")
    codes = {gen.encode(i) for i in range(1, 50_001)}
    assert len(codes) == 50_000


def test_sequential_ids_are_not_sequential_codes():
    gen = CodeGenerator("secret")
    a, b = gen.encode(1), gen.encode(2)
    assert abs(base62_decode(a) - base62_decode(b)) > 1000


def test_secret_changes_mapping():
    assert CodeGenerator("a").encode(42) != CodeGenerator("b").encode(42)


def test_out_of_range_id_rejected():
    gen = CodeGenerator("s")
    with pytest.raises(ValueError):
        gen.encode(MAX_ID + 1)
    with pytest.raises(ValueError):
        gen.encode(-1)
