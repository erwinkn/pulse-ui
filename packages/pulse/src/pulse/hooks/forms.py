from __future__ import annotations

from typing import TYPE_CHECKING, Callable, cast

from .core import HookMetadata, HookState, hooks

if TYPE_CHECKING:
    from ..form import ManualForm


class FormStorage(HookState):
    __slots__ = ("forms", "prev_forms", "render_mark")

    def __init__(self) -> None:
        super().__init__()
        self.forms: dict[str, "ManualForm"] = {}
        self.prev_forms: dict[str, "ManualForm"] = {}
        self.render_mark = 0

    def on_render_start(self, render_cycle: int) -> None:
        super().on_render_start(render_cycle)
        if self.render_mark == render_cycle:
            return
        self.prev_forms = self.forms
        self.forms = {}
        self.render_mark = render_cycle

    def on_render_end(self, render_cycle: int) -> None:
        if not self.prev_forms:
            return
        for form in self.prev_forms.values():
            form.dispose()
        self.prev_forms.clear()

    def register(
        self,
        key: str,
        factory: Callable[[], "ManualForm"],
    ) -> "ManualForm":
        if key in self.forms:
            raise RuntimeError(
                f"Duplicate ps.Form id '{key}' detected within the same render"
            )
        form = self.prev_forms.pop(key, None)
        if form is None:
            form = factory()
        self.forms[key] = form
        return form

    def dispose(self) -> None:
        for form in self.forms.values():
            form.dispose()
        for form in self.prev_forms.values():
            form.dispose()
        self.forms.clear()
        self.prev_forms.clear()


def _forms_factory():
    return FormStorage()


internal_forms_hook = hooks.create(
    "pulse:core.forms",
    _forms_factory,
    metadata=HookMetadata(
        owner="pulse.core",
        description="Internal storage for ps.Form manual forms",
    ),
)



__all__ = ["FormStorage", "internal_forms_hook"]
