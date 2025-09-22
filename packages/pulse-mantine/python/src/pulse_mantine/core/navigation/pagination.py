from typing import Optional
import pulse as ps


@ps.react_component("Pagination", "@mantine/core")
def Pagination(key: Optional[str] = None, **props): ...


@ps.react_component("Pagination", "@mantine/core", prop="Root")
def PaginationRoot(*children: ps.Child, key: Optional[str] = None, **props): ...


@ps.react_component("Pagination", "@mantine/core", prop="Control")
def PaginationControl(*children: ps.Child, key: Optional[str] = None, **props): ...


@ps.react_component("Pagination", "@mantine/core", prop="Dots")
def PaginationDots(key: Optional[str] = None, **props): ...


@ps.react_component("Pagination", "@mantine/core", prop="First")
def PaginationFirst(key: Optional[str] = None, **props): ...


@ps.react_component("Pagination", "@mantine/core", prop="Last")
def PaginationLast(key: Optional[str] = None, **props): ...


@ps.react_component("Pagination", "@mantine/core", prop="Next")
def PaginationNext(key: Optional[str] = None, **props): ...


@ps.react_component("Pagination", "@mantine/core", prop="Previous")
def PaginationPrevious(key: Optional[str] = None, **props): ...


@ps.react_component("Pagination", "@mantine/core", prop="Items")
def PaginationItems(*children: ps.Child, key: Optional[str] = None, **props): ...

