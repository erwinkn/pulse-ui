from typing import Any

import pulse as ps

_Table = ps.Import("Table", "@mantine/core")


@ps.react_component(_Table)
def Table(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Table.Thead)
def TableThead(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Table.Tbody)
def TableTbody(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Table.Tfoot)
def TableTfoot(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Table.Td)
def TableTd(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Table.Th)
def TableTh(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Table.Tr)
def TableTr(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Table.Caption)
def TableCaption(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Table.ScrollContainer)
def TableScrollContainer(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Table.DataRenderer)
def TableDataRenderer(key: str | None = None, **props: Any): ...
