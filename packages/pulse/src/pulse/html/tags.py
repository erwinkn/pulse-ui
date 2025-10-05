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


# Main TAGS list - defines all standard HTML tags
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
    # SVG tags
    ("svg", None),
    ("circle", None),
    ("ellipse", None),
    ("g", None),
    ("line", None),
    ("path", None),
    ("polygon", None),
    ("polyline", None),
    ("rect", None),
    ("text", None),
    ("tspan", None),
    ("defs", None),
    ("clipPath", None),
    ("mask", None),
    ("pattern", None),
    ("use", None),
]

# Self-closing tags list
SELF_CLOSING_TAGS = [
    ("area", None),
    ("base", None),
    ("br", None),
    ("col", None),
    ("embed", None),
    ("hr", None),
    ("img", None),
    ("input", None),
    ("link", None),
    ("meta", None),
    ("param", None),
    ("source", None),
    ("track", None),
    ("wbr", None),
]

# Create tag functions dynamically
globals_dict = globals()

# Regular tags
for name, default_props in TAGS:
    var_name = f"{name}_" if name == "del" else name
    globals_dict[var_name] = define_tag(name, default_props)

# Self-closing tags
for name, default_props in SELF_CLOSING_TAGS:
    globals_dict[name] = define_self_closing_tag(name, default_props)

# React fragment
fragment = define_tag("$$fragment")
