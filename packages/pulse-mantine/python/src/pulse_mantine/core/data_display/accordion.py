import pulse as ps


@ps.react_component("Accordion", "@mantine/core")
def Accordion(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Accordion", "@mantine/core", prop="Item")
def AccordionItem(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Accordion", "@mantine/core", prop="Panel")
def AccordionPanel(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Accordion", "@mantine/core", prop="Control")
def AccordionControl(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Accordion", "@mantine/core", prop="Chevron")
def AccordionChevron(key: str | None = None, **props): ...
