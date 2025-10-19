import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import (
	Any,
	Generic,
	Literal,
	TypeVar,
	Union,
	Unpack,
)

import pulse as ps
from pulse.helpers import call_flexible, create_task, maybe_await
from pulse.reactive_extensions import ReactiveDict
from pulse.serializer import deserialize

from .internal import FormInternal, FormMode
from .validators import (
	AsyncValidator,
	ServerValidation,
	Validation,
	Validator,
	serialize_validation,
)

FieldValue = str | int | float | bool | datetime | ps.UploadFile
FormValues = Mapping[str, Union[FieldValue, Sequence[FieldValue], "FormValues"]]

TForm = TypeVar("TForm", bound=FormValues)


class MantineFormProps(ps.HTMLFormProps, Generic[TForm], total=False):
	mode: FormMode
	validate: "Validation"
	initialValues: dict[str, Any]
	initialErrors: dict[str, Any]
	initialDirty: dict[str, bool]
	initialTouched: dict[str, bool]
	validateInputOnBlur: bool | list[str]
	validateInputOnChange: bool | list[str]
	clearInputErrorOnChange: bool
	cascadeUpdates: bool
	debounceMs: int
	touchTrigger: Literal["change", "focus"]
	"""touchTrigger option allows customizing events that change touched state.

    Options:
        change (default): Field is touched when value changes or has been focused
        focus: Field is touched only when it has been focused
    """
	onSubmit: ps.EventHandler1[TForm]  # pyright: ignore[reportIncompatibleVariableOverride]
	onReset: ps.EventHandler1[ps.FormEvent[ps.HTMLFormElement]]
	syncMode: Literal["none", "blur", "change"]


class MantineForm(ps.State, Generic[TForm]):
	def __init__(
		self,
		mode: FormMode | None = None,
		validate: "Validation | None" = None,
		initialValues: dict[str, Any] | None = None,
		initialErrors: dict[str, Any] | None = None,
		initialDirty: dict[str, bool] | None = None,
		initialTouched: dict[str, bool] | None = None,
		validateInputOnBlur: bool | list[str] | None = None,
		validateInputOnChange: bool | list[str] | None = None,
		clearInputErrorOnChange: bool | None = None,
		touchTrigger: Literal["change", "focus"] | None = None,
		syncMode: Literal["none", "blur", "change"] = "none",
		debounceMs: int | None = None,
	):
		self._channel = ps.channel()
		self._form = ps.ManualForm(on_submit=self._handle_form_data)
		self._sync_mode: Literal["none", "blur", "change"] = syncMode
		self._synced_values = ReactiveDict(initialValues or {})
		if self._sync_mode != "none":
			self._channel.on("syncValues", self._on_sync_values)
		# Listen for server-side validation requests from the client
		self._channel.on("serverValidate", self._on_server_validate)

		self._validation = validate
		self._mantine_props = {
			"mode": mode,
			"validate": serialize_validation(validate) if validate else None,
			"initialValues": initialValues,
			"initialErrors": initialErrors,
			"initialDirty": initialDirty,
			"initialTouched": initialTouched,
			"validateInputOnBlur": validateInputOnBlur,
			"validateInputOnChange": validateInputOnChange,
			"clearInputErrorOnChange": clearInputErrorOnChange,
			"debounceMs": debounceMs,
			"touchTrigger": touchTrigger,
			"syncMode": syncMode,
		}
		# Filter out None values
		self._mantine_props = {
			k: v for k, v in self._mantine_props.items() if v is not None
		}

		_check_for_reserved_keys(initialValues)
		_check_for_reserved_keys(initialErrors)
		_check_for_reserved_keys(initialDirty)
		_check_for_reserved_keys(initialTouched)

	async def _handle_form_data(self, data: ps.FormData):
		# Expect one JSON-serialized entry under "__data__" with v3 serializer
		# and remaining entries are files keyed by their dot/bracket paths.
		raw = data.get("__data__")
		base: dict[str, Any] = {}
		if isinstance(raw, str) and raw:
			try:
				payload = json.loads(raw)
				base = deserialize(payload)
			except Exception:
				base = {}

		# Merge file entries back into the nested structure
		files: dict[str, Any] = {k: v for k, v in data.items() if k != "__data__"}
		result = _merge_files_into_structure(base, files)

		# Run server-side validation for ALL rules before forwarding to user's onSubmit.
		# This mirrors Mantine behavior where onSubmit is called only if the form is valid.
		if not await self._validate_all_before_submit(result):
			return

		# Forward to user onSubmit if provided
		if self._on_submit is not None:
			await maybe_await(call_flexible(self._on_submit, result))  # pyright: ignore[reportArgumentType]

	# Mount the React component, wiring messages and passing through props
	def render(
		self,
		*children: ps.Child,
		key: str | None = None,
		onSubmit: ps.EventHandler1[TForm] | None = None,
		**props: Unpack[ps.HTMLFormProps],  # pyright: ignore[reportGeneralTypeIssues]
	):
		self._on_submit = onSubmit
		merged = {**props, **self._mantine_props, **self._form.props()}
		return FormInternal(
			*children,
			key=key,
			channelId=self._channel.id,
			**merged,
		)

	# Public API mapping to Mantine useForm actions
	async def get_form_values(self):
		return await self._channel.request("getFormValues")

	def set_values(self, values: dict[str, Any]):
		# Optimistically update server state if sync is enabled
		if self._sync_mode != "none" and isinstance(values, dict):
			incoming_keys = set(values.keys())
			for existing in list(self._synced_values.keys()):
				if existing not in incoming_keys:
					self._synced_values.delete(existing)
			self._synced_values.update(values)
		self._channel.emit("setValues", {"values": values})

	def set_field_value(self, path: str, value: Any):
		# Optimistically update server state if sync is enabled
		if self._sync_mode != "none" and isinstance(path, str):
			try:
				segments = _tokenize_path(path)
				_set_deep(self._synced_values, segments, value)
			except Exception:
				pass
		self._channel.emit("setFieldValue", {"path": path, "value": value})

	def insert_list_item(self, path: str, item: Any, index: int | None = None):
		msg: dict[str, Any] = {"path": path, "item": item}
		if index is not None:
			msg["index"] = index
		# Optimistically update server state if sync is enabled
		if self._sync_mode != "none" and isinstance(path, str):
			try:
				segments = _tokenize_path(path)
				parent, key = _get_parent_and_key(self._synced_values, segments)
				if isinstance(key, int) and isinstance(parent, list):
					insert_at = index if index is not None else len(parent)
					if insert_at < 0:
						insert_at = 0
					if insert_at > len(parent):
						insert_at = len(parent)
					parent.insert(insert_at, item)
				elif isinstance(key, str) and isinstance(parent, dict):
					# If the target is a list under a dict key
					lst = parent.get(key)
					if isinstance(lst, list):
						insert_at = index if index is not None else len(lst)
						if insert_at < 0:
							insert_at = 0
						if insert_at > len(lst):
							insert_at = len(lst)
						lst.insert(insert_at, item)
			except Exception:
				pass
		self._channel.emit("insertListItem", msg)

	def remove_list_item(self, path: str, index: int):
		# Optimistically update server state if sync is enabled
		if self._sync_mode != "none" and isinstance(path, str):
			try:
				segments = _tokenize_path(path)
				parent, key = _get_parent_and_key(self._synced_values, segments)
				lst = None
				if isinstance(key, int) and isinstance(parent, list):
					lst = parent
				elif isinstance(key, str) and isinstance(parent, dict):
					maybe = parent.get(key)
					if isinstance(maybe, list):
						lst = maybe
				if isinstance(lst, list) and 0 <= index < len(lst):
					lst.pop(index)
			except Exception:
				pass
		self._channel.emit("removeListItem", {"path": path, "index": index})

	def reorder_list_item(self, path: str, frm: int, to: int):
		# Optimistically update server state if sync is enabled
		if self._sync_mode != "none" and isinstance(path, str):
			try:
				segments = _tokenize_path(path)
				parent, key = _get_parent_and_key(self._synced_values, segments)
				lst = None
				if isinstance(key, int) and isinstance(parent, list):
					lst = parent
				elif isinstance(key, str) and isinstance(parent, dict):
					maybe = parent.get(key)
					if isinstance(maybe, list):
						lst = maybe
				if isinstance(lst, list) and 0 <= frm < len(lst) and 0 <= to < len(lst):
					item = lst.pop(frm)
					lst.insert(to, item)
			except Exception:
				pass
		self._channel.emit(
			"reorderListItem",
			{"path": path, "from": frm, "to": to},
		)

	def set_errors(self, errors: dict[str, Any]):
		self._channel.emit("setErrors", {"errors": errors})

	def set_field_error(self, path: str, error: Any):
		self._channel.emit("setFieldError", {"path": path, "error": error})

	def clear_errors(self, *paths: str):
		if paths:
			self._channel.emit("clearErrors", {"paths": list(paths)})
		else:
			self._channel.emit("clearErrors")

	def set_touched(self, touched: dict[str, bool]):
		self._channel.emit("setTouched", {"touched": touched})

	def validate(self):
		# Trigger client-side validation
		self._channel.emit("validate")
		# Also run all server-side validators in the background for current values
		create_task(self._validate_all_server_specs())

	async def _validate_all_server_specs(self) -> None:
		try:
			# Get latest values from client
			values: dict[str, Any] = await self._channel.request("getFormValues")
			# Collect all paths that have at least one ServerValidation spec
			schema = self._validation
			if not isinstance(schema, dict):
				return

			paths: list[str] = []

			def join(p: str, k: str) -> str:
				return f"{p}.{k}" if p else k

			def visit(node: Any, path: str) -> None:
				if isinstance(node, dict):
					root = node.get("formRootRule")
					if root is not None:
						visit(root, path)
					for k, v in node.items():
						if k == "formRootRule":
							continue
						visit(v, join(path, k))
					return
				if isinstance(node, list):
					has_server = any(
						isinstance(spec, ServerValidation) for spec in node
					)
					if has_server:
						paths.append(path)
					return
				if isinstance(node, ServerValidation):
					paths.append(path)

			visit(schema, "")

			for path in paths:
				payload = {
					"value": None,  # value will be recomputed in handler using values + path
					"values": values,
					"path": path,
				}
				await self._on_server_validate(payload)
		except Exception:
			return

	def reset(self, initial_values: dict[str, Any] | None = None):
		if initial_values is not None:
			self._channel.emit("reset", {"initialValues": initial_values})
		else:
			self._channel.emit("reset")

	@property
	def values(self) -> ReactiveDict[str, Any]:
		if self._sync_mode == "none":
			raise ValueError(
				'Form values are only accessible on the server when syncMode="change" or syncMode="blur"'
			)
		return self._synced_values

	# --- internal sync handling -------------------------------------------------
	def _on_sync_values(self, payload: dict[str, Any]) -> None:
		values = payload.get("values")
		if not isinstance(values, dict):
			return
		incoming_keys = set(values.keys())
		for existing in list(self._synced_values.keys()):
			if existing not in incoming_keys:
				self._synced_values.delete(existing)
		self._synced_values.update(values)

	# Channel handler for server validation (single entrypoint)
	async def _on_server_validate(self, payload: dict[str, Any]) -> None:
		try:
			value = payload.get("value")
			values = payload.get("values")
			path = payload.get("path")
			if not isinstance(values, dict) or not isinstance(path, str):
				return

			schema = self._validation
			if not isinstance(schema, dict):
				return

			# Traverse schema by path segments, skipping numeric indices
			node: Any = schema
			for seg in str(path).split("."):
				if isinstance(node, dict):
					# Skip numeric segments (list indices)
					if seg.isdigit():
						continue
					nxt = node.get(seg)
					if nxt is None:
						# Try root-level rule fallback
						nxt = node.get("formRootRule")
					node = nxt
				else:
					break

			# Node can be a spec, a list of specs, or nested dict
			specs: list[Validator] = []
			if isinstance(node, dict):
				node = node.get("formRootRule")
			if isinstance(node, list):
				specs = [s for s in node if isinstance(s, Validator)]
			if isinstance(node, Validator):
				specs = [node]

			# Invoke server validators, stop on first error
			for spec in specs:
				if isinstance(spec, ServerValidation):
					try:
						res = await spec.acheck(value, values, path)
						if isinstance(res, str) and res:
							self.set_field_error(path, res)
							return
					except Exception:
						# Do not crash validation on server errors; surface generic error
						self.set_field_error(path, "Validation failed")
						return
			self.clear_errors(path)
		except Exception:
			# best-effort; do not crash channel
			return

	# Validate all rules during submit (client and server equivalents)
	async def _validate_all_before_submit(self, values: dict[str, Any]) -> bool:
		schema = self._validation
		if not isinstance(schema, dict):
			return True

		errors: dict[str, Any] = {}

		def join(p: str, k: str) -> str:
			return f"{p}.{k}" if p else k

		def get_value_at_path(source: Any, path: str) -> Any:
			cur = source
			for seg in str(path).split("."):
				if seg == "":
					continue
				if isinstance(cur, list) and seg.isdigit():
					idx = int(seg)
					if idx < 0 or idx >= len(cur):
						return None
					cur = cur[idx]
				elif isinstance(cur, dict):
					cur = cur.get(seg)
				else:
					return None
			return cur

		async def apply_node(node: Any, path: str) -> None:
			# If nested dict contains root-level rule, apply it to current path
			if isinstance(node, dict):
				root = node.get("formRootRule")
				if root is not None:
					await apply_node(root, path)
				for k, v in node.items():
					if k == "formRootRule":
						continue
					await apply_node(v, join(path, k))
				return
			# List of specs
			if isinstance(node, list):
				for spec in node:
					await apply_node(spec, path)
				return
			# Single validator
			if isinstance(node, Validator):
				try:
					value = get_value_at_path(values, path)
					# Prefer async if available
					if isinstance(node, AsyncValidator):
						res = await node.acheck(value, values, path)
					else:
						res = node.check(value, values, path)
					if isinstance(res, str) and res:
						errors[path] = res
				except Exception:
					errors[path] = "Validation failed"
				return

		await apply_node(schema, "")

		if errors:
			self.set_errors(errors)
			return False
		return True


# Also ensure user data objects do not contain reserved keys
def _check_for_reserved_keys(obj: Any, path: str = "") -> None:
	if isinstance(obj, dict):
		for k, v in obj.items():
			if k in {"$kind", "formRootRule"}:
				raise ValueError(
					"'$kind' and 'formRootRule' are reserved keys and cannot appear in user data"
				)
			_check_for_reserved_keys(v, f"{path}.{k}" if path else str(k))
	elif isinstance(obj, list):
		for idx, v in enumerate(obj):
			_check_for_reserved_keys(v, f"{path}[{idx}]")


def _merge_files_into_structure(base: Any, files: dict[str, Any]) -> Any:
	result = _deep_copy(base)

	# Expand lists of files into multiple insert operations
	def iter_entries():
		for path, value in files.items():
			if isinstance(value, list):
				for item in value:
					yield (path, item)
			else:
				yield (path, value)

	for path, value in iter_entries():
		segments = _tokenize_path(path)
		_set_deep(result, segments, value)
	return result


def _deep_copy(obj: Any) -> Any:
	if isinstance(obj, dict):
		return {k: _deep_copy(v) for k, v in obj.items()}
	if isinstance(obj, list):
		return [_deep_copy(v) for v in obj]
	return obj


def _tokenize_path(path: str) -> list[str]:
	# Convert bracket notation to dots: a[0].b -> a.0.b
	out: list[str] = []
	buf = ""
	i = 0
	while i < len(path):
		ch = path[i]
		if ch == "[":
			if buf:
				out.append(buf)
				buf = ""
			j = i + 1
			num = ""
			while j < len(path) and path[j] != "]":
				num += path[j]
				j += 1
			if num:
				out.append(num)
			i = j + 1
			if i < len(path) and path[i] == ".":
				i += 1
			continue
		elif ch == ".":
			if buf:
				out.append(buf)
				buf = ""
		else:
			buf += ch
		i += 1
	if buf:
		out.append(buf)
	return [seg for seg in out if seg]


def _ensure_container(parent: Any, key: str | int, next_is_index: bool):
	if isinstance(key, int):
		# Parent must be a list
		if not isinstance(parent, list):
			return []
		# Ensure capacity
		while len(parent) <= key:
			parent.append(None)
		child = parent[key]
		if child is None:
			parent[key] = [] if next_is_index else {}
			child = parent[key]
		return child
	else:
		if not isinstance(parent, dict):
			return {}
		child = parent.get(key)
		if child is None:
			parent[key] = [] if next_is_index else {}
			child = parent[key]
		return child


def _set_deep(root: Any, segments: list[str], value: Any) -> None:
	# Walk creating containers as needed; set or append at leaf
	cur = root
	for idx, raw_seg in enumerate(segments):
		is_last = idx == len(segments) - 1
		is_index = raw_seg.isdigit()
		seg: int | str = int(raw_seg) if is_index else raw_seg
		if is_last:
			if isinstance(seg, int):
				if not isinstance(cur, list):
					return
				while len(cur) <= seg:
					cur.append(None)
				existing = cur[seg]
				if existing is None:
					cur[seg] = value
				else:
					if isinstance(existing, list):
						existing.append(value)
					else:
						cur[seg] = [existing, value]
			else:
				if not isinstance(cur, dict):
					return
				existing = cur.get(seg)
				if existing is None:
					cur[seg] = value
				else:
					if isinstance(existing, list):
						existing.append(value)
					else:
						cur[seg] = [existing, value]
		else:
			next_is_index = segments[idx + 1].isdigit()
			child = _ensure_container(cur, seg, next_is_index)
			# Attach child back to parent in case container was created
			if isinstance(seg, int):
				if not isinstance(cur, list):
					return
				while len(cur) <= seg:
					cur.append(None)
				cur[seg] = child
			else:
				if not isinstance(cur, dict):
					return
				cur[seg] = child
			cur = child


def _walk_to_parent(root: Any, segments: list[str]) -> tuple[Any, str | int]:
	cur = root
	for idx, raw_seg in enumerate(segments):
		is_last = idx == len(segments) - 1
		is_index = raw_seg.isdigit()
		seg: int | str = int(raw_seg) if is_index else raw_seg
		if is_last:
			return cur, seg
		next_is_index = segments[idx + 1].isdigit()
		child = _ensure_container(cur, seg, next_is_index)
		if isinstance(seg, int):
			if not isinstance(cur, list):
				return cur, seg
			while len(cur) <= seg:
				cur.append(None)
			cur[seg] = child
		else:
			if not isinstance(cur, dict):
				return cur, seg
			cur[seg] = child
		cur = child
	return cur, segments[-1] if segments else ""


def _get_parent_and_key(root: Any, segments: list[str]) -> tuple[Any, str | int]:
	return _walk_to_parent(root, segments)
