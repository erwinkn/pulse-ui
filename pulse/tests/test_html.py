import pytest
from pulse.html import (
    html,
    head,
    title,
    body,
    div,
    p,
    span,
    br,
    img,
    a,
    script,
    pre,
    code,
    style,
    form,
    input,
    textarea,
    link,
    meta,
    strong,
)


def indent(text: str, spaces: int):
    return (" " * spaces) + text


def test_basic_tags():
    """Test basic tag rendering without attributes"""
    assert div().render() == "<div></div>"
    assert p().render() == "<p></p>"
    assert span().render() == "<span></span>"


def test_self_closing_tags():
    """Test self-closing tags render correctly"""
    assert br().render() == "<br />"
    assert img().render() == "<img />"
    assert meta().render() == "<meta />"


def test_attributes():
    """Test tags with attributes"""
    assert div(classname="container").render() == '<div class="container"></div>'
    assert (
        a(href="https://example.com")().render() == '<a href="https://example.com"></a>'
    )
    assert (
        img(src="/img.jpg", alt="An image").render()
        == '<img src="/img.jpg" alt="An image" />'
    )


def test_nested_elements():
    """Test nested element structures"""
    doc = html(
        head(title("My Page")), body(div(classname="container")(p("Hello, world!")))
    )
    expected = "\n".join(
        [
            "<!DOCTYPE html>",
            "<html>",
            indent("<head>", 2),
            indent("<title>", 4),
            indent("My Page", 6),
            indent("</title>", 4),
            indent("</head>", 2),
            indent("<body>", 2),
            indent('<div class="container">', 4),
            indent("<p>", 6),
            indent("Hello, world!", 8),
            indent("</p>", 6),
            indent("</div>", 4),
            indent("</body>", 2),
            "</html>",
        ]
    )
    assert doc.render() == expected


def test_whitespace_sensitive():
    """Test whitespace-sensitive elements preserve formatting"""
    code_block = pre(
        code("""def hello():
    print("Hello, world!")
    return 42""")
    )
    expected = (
        "<pre><code>def hello():\n"
        "    print(&quot;Hello, world!&quot;)\n"
        "    return 42</code></pre>"
    )
    assert code_block.render(indent=2) == expected


def test_default_attributes():
    """Test tags with default attributes"""
    assert script().render() == '<script type="text/javascript"></script>'
    assert style().render() == '<style type="text/css"></style>'
    assert form().render() == '<form method="POST"></form>'


def test_attribute_escaping():
    """Test proper escaping of attribute values"""
    assert (
        div(data_value="<>\"'&").render()
        == '<div data-value="&lt;&gt;&quot;&#x27;&amp;"></div>'
    )


def test_content_escaping():
    """Test proper escaping of content"""
    assert p('<script>alert("xss")</script>').render() == "\n".join(
        [
            "<p>",
            indent("&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;", 2),
            "</p>",
        ]
    )


def test_mixed_content():
    """Test mixing text and elements as children"""
    doc = p("Start ", strong("important"), " end")
    expected = "\n".join(
        [
            "<p>",
            indent("Start ", 2),
            indent("<strong>", 2),
            indent("important", 4),
            indent("</strong>", 2),
            indent(" end", 2),
            "</p>",
        ]
    )
    assert doc.render() == expected


def test_indexing_syntax():
    """Test new indexing syntax for passing children"""
    # Basic indexing with single child
    element = div(id='container', class_='wrapper')[p("Hello!")]
    expected = "\n".join([
        '<div id="container" class="wrapper">',
        indent("<p>", 2),
        indent("Hello!", 4),
        indent("</p>", 2),
        "</div>",
    ])
    assert element.render() == expected

    # Indexing with multiple children using tuple
    element = div(id='container')[p("First"), p("Second")]
    expected = "\n".join([
        '<div id="container">',
        indent("<p>", 2),
        indent("First", 4),
        indent("</p>", 2),
        indent("<p>", 2),
        indent("Second", 4),
        indent("</p>", 2),
        "</div>",
    ])
    assert element.render() == expected

    # Mixed content with indexing
    element = div(class_='content')["Text ", strong("bold"), " more text"]
    expected = "\n".join([
        '<div class="content">',
        indent("Text ", 2),
        indent("<strong>", 2),
        indent("bold", 4),
        indent("</strong>", 2),
        indent(" more text", 2),
        "</div>",
    ])
    assert element.render() == expected


def test_invalid_usage():
    """Test error cases"""
    # Self-closing tags cannot have children
    with pytest.raises(ValueError):
        img()(p("Invalid"))

    # Self-closing tags cannot have children with indexing
    with pytest.raises(ValueError):
        img()[p("Invalid")]

    # Cannot pass both children and attributes at once
    with pytest.raises(ValueError):
        div(p("Invalid"), classname="container")

    # Cannot pass children twice
    with pytest.raises(ValueError):
        div(p())(p())

    # Cannot use indexing after already having children
    with pytest.raises(TypeError):
        div(p())[p()]

    # Cannot use call after indexing
    with pytest.raises(ValueError):
        div()[p()](p())


if __name__ == "__main__":
    pytest.main([__file__])
