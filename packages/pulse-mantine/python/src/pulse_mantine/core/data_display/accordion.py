from typing import Any

import pulse as ps

_Accordion = ps.Import("Accordion", "@mantine/core")


@ps.react_component(_Accordion)
def Accordion(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Accordion.Item)
def AccordionItem(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Accordion.Panel)
def AccordionPanel(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Accordion.Control)
def AccordionControl(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Accordion.Chevron)
def AccordionChevron(key: str | None = None, **props: Any): ...
