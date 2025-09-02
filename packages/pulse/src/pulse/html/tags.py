from typing import Any, ParamSpec
from pulse.vdom import Node, Element


P = ParamSpec("P")


def define_tag(name: str, default_props: dict[str, Any] | None = None):
    """
    Define a standard HTML tag that creates UITreeNode instances.

    Args:
        name: The tag name (e.g., "div", "span")
        default_props: Default props to apply to all instances

    Returns:
        A function that creates UITreeNode instances
    """

    def create_element(*children: Element, **props: Any) -> Node:
        """Create a UITreeNode for this tag."""
        if default_props:
            props = default_props | props
        return Node(tag=name, props=props, children=children)

    return create_element


def define_self_closing_tag(name: str, default_props: dict[str, Any] | None = None):
    """
    Define a self-closing HTML tag that creates UITreeNode instances.

    Args:
        name: The tag name (e.g., "br", "img")
        default_props: Default props to apply to all instances

    Returns:
        A function that creates UITreeNode instances (no children allowed)
    """
    default_props = default_props

    def create_element(**props: Any) -> Node:
        """Create a self-closing UITreeNode for this tag."""
        if default_props:
            props = default_props | props
        return Node(
            tag=name,
            props=props,
            children=(),  # Self-closing tags never have children
            allow_children=False,
        )

    return create_element


# Regular tags with their default props (if any)
TAGS = [
    ("a", None),
    ("abbr", None),
    ("address", None),
    ("article", None),
    ("aside", None),
    ("audio", None),
    ("b", None),
    ("bdi", None),
    ("bdo", None),
    ("blockquote", None),
    ("body", None),
    ("button", None),
    ("canvas", None),
    ("caption", None),
    ("cite", None),
    ("code", None),
    ("colgroup", None),
    ("data", None),
    ("datalist", None),
    ("dd", None),
    ("del", None),
    ("details", None),
    ("dfn", None),
    ("dialog", None),
    ("div", None),
    ("dl", None),
    ("dt", None),
    ("em", None),
    ("fieldset", None),
    ("figcaption", None),
    ("figure", None),
    ("footer", None),
    ("form", {"method": "POST"}),
    ("h1", None),
    ("h2", None),
    ("h3", None),
    ("h4", None),
    ("h5", None),
    ("h6", None),
    ("head", None),
    ("header", None),
    ("hgroup", None),
    ("html", None),
    ("i", None),
    ("iframe", None),
    ("ins", None),
    ("kbd", None),
    ("label", None),
    ("legend", None),
    ("li", None),
    ("main", None),
    ("map", None),
    ("mark", None),
    ("menu", None),
    ("meter", None),
    ("nav", None),
    ("noscript", None),
    ("object", None),
    ("ol", None),
    ("optgroup", None),
    ("option", None),
    ("output", None),
    ("p", None),
    ("picture", None),
    ("pre", None),
    ("progress", None),
    ("q", None),
    ("rp", None),
    ("rt", None),
    ("ruby", None),
    ("s", None),
    ("samp", None),
    ("script", {"type": "text/javascript"}),
    ("section", None),
    ("select", None),
    ("small", None),
    ("span", None),
    ("strong", None),
    ("style", {"type": "text/css"}),
    ("sub", None),
    ("summary", None),
    ("sup", None),
    ("table", None),
    ("tbody", None),
    ("td", None),
    ("template", None),
    ("textarea", None),
    ("tfoot", None),
    ("th", None),
    ("thead", None),
    ("time", None),
    ("title", None),
    ("tr", None),
    ("u", None),
    ("ul", None),
    ("var", None),
    ("video", None),
]

for tag_name, default_props in TAGS:
    # Handle special cases where Python name needs to be different
    fn_name = f"{tag_name}_" if tag_name == "del" else tag_name
    globals()[fn_name] = define_tag(tag_name, default_props)


# Self-closing tags
# Create all self-closing tags from a list
SELF_CLOSING_TAGS = [
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
]
for tag_name in SELF_CLOSING_TAGS:
    globals()[tag_name] = define_self_closing_tag(tag_name)

# React fragment
fragment = define_tag("$$fragment")
