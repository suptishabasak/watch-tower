import ipaddress

import pytest

from app.security import UnsafeURLError, is_public_ip, validate_public_url


def fake_resolver(mapping):
    def resolve(host):
        return [ipaddress.ip_address(ip) for ip in mapping[host]]

    return resolve


PUBLIC = fake_resolver({"example.com": ["93.184.216.34"], "www.example.com": ["93.184.216.34"]})


def test_accepts_public_https_url():
    assert validate_public_url("https://example.com/page?x=1", PUBLIC) == "https://example.com/page?x=1"


def test_adds_https_when_scheme_missing():
    assert validate_public_url("example.com", PUBLIC) == "https://example.com"


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/",
        "javascript:alert(1)",
        "http://localhost/",
        "http://localhost:8080/",
        "http://foo.localhost/",
        "http://printer.local/",
        "http://db.internal/",
        "http://127.0.0.1/",
        "http://10.0.0.5/",
        "http://172.16.0.1/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://0.0.0.0/",
        "http://100.64.0.1/",
        "http://intranet/",
        "https://user:pass@example.com/",
        "https://example.com:22/",
        "http://",
        "",
    ],
)
def test_rejects_unsafe_urls(url):
    with pytest.raises(UnsafeURLError):
        validate_public_url(url, PUBLIC)


def test_rejects_hostname_resolving_to_private_ip():
    resolver = fake_resolver({"evil.example.com": ["10.1.2.3"]})
    with pytest.raises(UnsafeURLError):
        validate_public_url("https://evil.example.com/", resolver)


def test_rejects_if_any_resolved_address_is_private():
    resolver = fake_resolver({"mixed.example.com": ["93.184.216.34", "127.0.0.1"]})
    with pytest.raises(UnsafeURLError):
        validate_public_url("https://mixed.example.com/", resolver)


def test_rejects_unresolvable_domain():
    def boom(host):
        raise UnsafeURLError("The domain could not be found.")

    with pytest.raises(UnsafeURLError):
        validate_public_url("https://nope.example.com/", boom)


@pytest.mark.parametrize("ip,expected", [
    ("8.8.8.8", True),
    ("1.1.1.1", True),
    ("2606:4700:4700::1111", True),
    ("127.0.0.1", False),
    ("10.0.0.1", False),
    ("169.254.169.254", False),
    ("::1", False),
    ("fe80::1", False),
    ("fc00::1", False),
    ("::ffff:10.0.0.1", False),
    ("224.0.0.1", False),
    ("64:ff9b::7f00:1", False),
])
def test_is_public_ip(ip, expected):
    assert is_public_ip(ip) is expected