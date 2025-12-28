from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Table", "@mantine/core"))
def Table(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Table", "@mantine/core", prop="Thead"))
def TableThead(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Table", "@mantine/core", prop="Tbody"))
def TableTbody(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Table", "@mantine/core", prop="Tfoot"))
def TableTfoot(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Table", "@mantine/core", prop="Td"))
def TableTd(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Table", "@mantine/core", prop="Th"))
def TableTh(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Table", "@mantine/core", prop="Tr"))
def TableTr(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Table", "@mantine/core", prop="Caption"))
def TableCaption(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Table", "@mantine/core", prop="ScrollContainer"))
def TableScrollContainer(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Table", "@mantine/core", prop="DataRenderer"))
def TableDataRenderer(key: str | None = None, **props: Any): ...
