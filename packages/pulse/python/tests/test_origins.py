import pytest
from pulse.origins import normalize_http_origin


@pytest.mark.parametrize(
	("value", "expected"),
	[
		("HTTP://EXAMPLE.COM:80/", "http://example.com"),
		("https://EXAMPLE.COM:443", "https://example.com"),
		("http://localhost:8000", "http://localhost:8000"),
		("http://[::1]:8000", "http://[::1]:8000"),
	],
)
def test_normalize_http_origin(value: str, expected: str) -> None:
	assert normalize_http_origin(value) == expected


@pytest.mark.parametrize(
	"value",
	[
		"",
		"example.com",
		"ftp://example.com",
		"http://example.com bad",
		"http://user@example.com",
		"http://example.com/path",
		"http://example.com?query=1",
		"http://example.com#fragment",
	],
)
def test_normalize_http_origin_rejects_non_origins(value: str) -> None:
	with pytest.raises(ValueError, match="backend"):
		normalize_http_origin(value, name="backend")


def test_normalize_http_origin_can_require_https() -> None:
	with pytest.raises(ValueError, match="public_origin must use HTTPS"):
		normalize_http_origin(
			"http://example.com",
			name="public_origin",
			require_https=True,
		)
