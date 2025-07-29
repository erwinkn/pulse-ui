import pytest
from pulse.html import (
    html,
    head,
    render,
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
    meta,
    strong,
)


def indent(text: str, spaces: int):
    return (" " * spaces) + text


def test_basic_tags():
    """Test basic tag rendering without attributes"""
    assert render(div()) == "<div></div>"
    assert render(p()) == "<p></p>"
    assert render(span()) == "<span></span>"


def test_self_closing_tags():
    """Test self-closing tags render correctly"""
    assert render(br()) == "<br />"
    assert render(img()) == "<img />"
    assert render(meta()) == "<meta />"


def test_attributes():
    """Test tags with attributes"""
    assert render(div(classname="container")) == '<div class="container"></div>'
    assert (
        render(a(href="https://example.com")) == '<a href="https://example.com"></a>'
    )
    assert (
        render(img(src="/img.jpg", alt="An image"))
        == '<img src="/img.jpg" alt="An image" />'
    )


def test_nested_elements():
    """Test nested element structures"""
    doc = html(
        head(title("My Page")), body(div(classname="container")[p("Hello, world!")])
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
    assert render(doc) == expected


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
    assert render(code_block, indent=2) == expected


def test_default_attributes():
    """Test tags with default attributes"""
    assert render(script()) == '<script type="text/javascript"></script>'
    assert render(style()) == '<style type="text/css"></style>'
    assert render(form()) == '<form method="POST"></form>'


def test_attribute_escaping():
    """Test proper escaping of attribute values"""
    assert (
        render(div(data_value="<>\"'&"))
        == '<div data-value="&lt;&gt;&quot;&#x27;&amp;"></div>'
    )


def test_content_escaping():
    """Test proper escaping of content"""
    assert render(p('<script>alert("xss")</script>')) == "\n".join(
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
    assert render(doc) == expected


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
    assert render(element) == expected

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
    assert render(element) == expected

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
    assert render(element) == expected


def test_invalid_usage():
    """Test error cases"""
    # Self-closing tags cannot have children
    with pytest.raises(TypeError):
        img()(p("Invalid")) # type: ignore

    # Self-closing tags cannot have children with indexing
    with pytest.raises(ValueError):
        img()[p("Invalid")]

    # Cannot pass children twice
    with pytest.raises(TypeError):
        div(p())(p()) # type: ignore

    # Cannot use indexing after already having children
    with pytest.raises(ValueError):
        div(p())[p()]

    # Cannot use call after indexing
    with pytest.raises(TypeError):
        div()[p()](p()) # type: ignore

if __name__ == "__main__":
    pytest.main([__file__])
