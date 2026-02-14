import runpy
from pathlib import Path
from typing import get_args

import pulse as ps


def test_error_types_example_defines_app_and_covers_all_error_codes():
	root = Path(__file__).resolve().parents[4]
	module = runpy.run_path(str(root / "examples" / "error_types.py"))

	assert isinstance(module["app"], ps.App)
	assert tuple(module["ERROR_CODES"]) == tuple(get_args(ps.ErrorCode))
