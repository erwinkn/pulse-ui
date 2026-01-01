from typing import Any

import pulse as ps

_Pagination = ps.Import("Pagination", "@mantine/core")


@ps.react_component(_Pagination)
def Pagination(key: str | None = None, **props: Any): ...


@ps.react_component(_Pagination.Root)
def PaginationRoot(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Pagination.Control)
def PaginationControl(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Pagination.Dots)
def PaginationDots(key: str | None = None, **props: Any): ...


@ps.react_component(_Pagination.First)
def PaginationFirst(key: str | None = None, **props: Any): ...


@ps.react_component(_Pagination.Last)
def PaginationLast(key: str | None = None, **props: Any): ...


@ps.react_component(_Pagination.Next)
def PaginationNext(key: str | None = None, **props: Any): ...


@ps.react_component(_Pagination.Previous)
def PaginationPrevious(key: str | None = None, **props: Any): ...


@ps.react_component(_Pagination.Items)
def PaginationItems(*children: ps.Node, key: str | None = None, **props: Any): ...
