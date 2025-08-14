from typing import Annotated, NotRequired, Optional, TypeVar, TypedDict, Unpack
import pulse as ps


class AccordionProps(TypedDict):
    open: bool
    key: str


print("Required keys:", getattr(AccordionProps, "__required_keys__", None))
print("Optional keys:", getattr(AccordionProps, "__optional_keys__", None))
print("Total:", getattr(AccordionProps, "__total__", None))