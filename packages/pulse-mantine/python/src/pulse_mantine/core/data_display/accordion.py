from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Accordion", "@mantine/core"))
def Accordion(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Accordion", "@mantine/core", prop="Item"))
def AccordionItem(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Accordion", "@mantine/core", prop="Panel"))
def AccordionPanel(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Accordion", "@mantine/core", prop="Control"))
def AccordionControl(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Accordion", "@mantine/core", prop="Chevron"))
def AccordionChevron(key: str | None = None, **props: Any): ...
