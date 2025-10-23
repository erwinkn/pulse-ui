from __future__ import annotations

import secrets
from pathlib import Path


def resolve_dev_secret(app_path: Path | None) -> str | None:
	"""Return or create a persisted development secret for the given app path."""
	if app_path is None:
		return None

	try:
		root = app_path if app_path.is_dir() else app_path.parent
		secret_dir = root / ".pulse"
		secret_dir.mkdir(parents=True, exist_ok=True)

		secret_file = secret_dir / "secret"
		if secret_file.exists():
			try:
				content = secret_file.read_text().strip()
				if content:
					return content
			except Exception:
				return None

		secret_value = secrets.token_urlsafe(32)
		try:
			secret_file.write_text(secret_value)
		except Exception:
			# Best effort; secret still returned for current session
			pass

		_gitignore = root / ".gitignore"
		try:
			if _gitignore.exists():
				content = _gitignore.read_text()
				if ".pulse/" not in content:
					_gitignore.write_text(f"{content.rstrip()}\n.pulse/\n")
			else:
				_gitignore.write_text(".pulse/\n")
		except Exception:
			# Non-fatal; ignore gitignore failures
			pass

		return secret_value
	except Exception:
		return None
