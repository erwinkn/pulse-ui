"""HTTP origin validation and normalization."""

from urllib.parse import urlsplit


def normalize_http_origin(
	value: str,
	*,
	name: str = "origin",
	require_https: bool = False,
) -> str:
	"""Validate and normalize an HTTP(S) origin."""
	if not value or any(char.isspace() for char in value):
		raise ValueError(f"{name} must be a valid HTTP(S) origin")
	try:
		parsed = urlsplit(value)
		port = parsed.port
	except ValueError as exc:
		raise ValueError(f"{name} must be a valid HTTP(S) origin") from exc

	scheme = parsed.scheme.lower()
	if (
		scheme not in ("http", "https")
		or not parsed.hostname
		or parsed.username is not None
		or parsed.password is not None
		or parsed.path not in ("", "/")
		or parsed.query
		or parsed.fragment
	):
		raise ValueError(
			f"{name} must be an HTTP(S) origin without credentials, a path, query, or fragment"
		)
	if require_https and scheme != "https":
		raise ValueError(f"{name} must use HTTPS")

	host = parsed.hostname.lower()
	if ":" in host:
		host = f"[{host}]"
	default_port = (scheme, port) in (("http", 80), ("https", 443))
	authority = host if port is None or default_port else f"{host}:{port}"
	return f"{scheme}://{authority}"
