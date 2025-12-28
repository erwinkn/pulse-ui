from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Pagination", "@mantine/core"))
def Pagination(key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Pagination", "@mantine/core", prop="Root"))
def PaginationRoot(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Pagination", "@mantine/core", prop="Control"))
def PaginationControl(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Pagination", "@mantine/core", prop="Dots"))
def PaginationDots(key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Pagination", "@mantine/core", prop="First"))
def PaginationFirst(key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Pagination", "@mantine/core", prop="Last"))
def PaginationLast(key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Pagination", "@mantine/core", prop="Next"))
def PaginationNext(key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Pagination", "@mantine/core", prop="Previous"))
def PaginationPrevious(key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Pagination", "@mantine/core", prop="Items"))
def PaginationItems(*children: ps.Node, key: str | None = None, **props: Any): ...
