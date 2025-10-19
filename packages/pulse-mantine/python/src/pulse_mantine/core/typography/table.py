import pulse as ps


@ps.react_component("Table", "@mantine/core")
def Table(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Table", "@mantine/core", prop="Thead")
def TableThead(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Table", "@mantine/core", prop="Tbody")
def TableTbody(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Table", "@mantine/core", prop="Tfoot")
def TableTfoot(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Table", "@mantine/core", prop="Td")
def TableTd(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Table", "@mantine/core", prop="Th")
def TableTh(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Table", "@mantine/core", prop="Tr")
def TableTr(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Table", "@mantine/core", prop="Caption")
def TableCaption(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Table", "@mantine/core", prop="ScrollContainer")
def TableScrollContainer(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Table", "@mantine/core", prop="DataRenderer")
def TableDataRenderer(key: str | None = None, **props): ...
