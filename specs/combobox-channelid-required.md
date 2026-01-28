# Combobox channelId required plan

Goal: Combobox always wired to channel/store for Python imperative control. Remove optional payloads/guards.

Scope
- JS: `packages/pulse-mantine/js/src/combobox.tsx`
- Python: `packages/pulse-mantine/python/src/pulse_mantine/core/combobox/combobox.py`
- Exports/stubs: `packages/pulse-mantine/python/src/pulse_mantine/__init__.py`, `.pyi`, JS `index.ts` if needed
- Examples: `examples/pulse-mantine/07-combobox.py`
- Tests: `packages/pulse-mantine/python/tests/test_combobox_store.py`

Plan
1. JS combobox
   - Make `channelId: string` required in `PulseComboboxProps`.
   - Call `usePulseChannel(channelId)` unconditionally; remove conditional hook.
   - Make channel handlers require payload shapes (no `?` types, no guards).
2. Python combobox API
   - Make `Combobox` require `store: ComboboxStore` (no `store=None` path).
   - Ensure store always passes `channelId` to `ComboboxInternal`.
   - Make `open_dropdown/close_dropdown/toggle_dropdown` require `event_source` (default to "unknown" and always send payload).
   - Make `update_selected_option_index` require `target` (default to "active" and always send payload).
   - Simplify event handlers to assume payload shape; drop `_event_source_from_payload` helper.
3. Examples
   - Give every Combobox a `ComboboxStore` (including inline example).
4. Tests
   - Update tests for required args and payloads.
   - Add a minimal test that `Combobox` without store raises `TypeError` (if runtime check stays implicit).
5. Run
   - `make test` (required).

Notes
- Breaking change: Combobox without store no longer supported. Document in CHANGELOG if required.
