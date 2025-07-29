"""
Integration tests for the complete Pulse UI system.

This module tests the full pipeline from Python UI tree definition
through TypeScript code generation and React component integration.
"""

import pytest
import json
import tempfile
import os
from pathlib import Path
from pulse.nodes import (
    define_react_component,
    get_registered_components,
    div,
    h1,
    h2,
    h3,
    p,
    button,
    ul,
    li,
    span,
    strong,
    article,
)
from pulse.route import define_route
from pulse.codegen import write_generated_files


class TestFullPipeline:
    """Test the complete pipeline from Python to TypeScript."""

    def setUp(self):
        """Clear the component registry before each test."""
        if hasattr(define_react_component, "_components"):
            define_react_component._components.clear()

    def test_simple_app_generation(self):
        """Test generating a simple app with multiple routes."""
        self.setUp()

        # Define React components
        Header = define_react_component(
            "header", "./components/Header", "Header", False
        )
        Footer = define_react_component(
            "footer", "./components/Footer", "Footer", False
        )
        Button = define_react_component(
            "button", "./components/Button", "Button", False
        )

        # Define routes
        @define_route("/", components=[])
        def home_route():
            return div(className="home")[
                h1()["Welcome to Pulse UI"],
                p()["This is a server-rendered home page."],
                p()["Navigate to other pages to see React components in action."],
            ]

        @define_route("/about", components=["header", "footer"])
        def about_route():
            return div(className="page")[
                Header(title="About Page"),
                div(className="content")[
                    h2()["About Us"],
                    p()["This page demonstrates server-rendered React components."],
                    p()[
                        "The header and footer are React components with server-provided props."
                    ],
                ],
                Footer(year=2024, company="Pulse UI"),
            ]

        @define_route("/interactive", components=["button"])
        def interactive_route():
            return div(className="interactive")[
                h1()["Interactive Demo"],
                p()["This page shows interactive React components:"],
                Button(variant="primary", size="large")["Click Me!"],
                Button(variant="secondary")["Another Button"],
                p()["These buttons will be fully interactive once hydrated."],
            ]

        routes = [home_route, about_route, interactive_route]

        # Generate files
        with tempfile.TemporaryDirectory() as temp_dir:
            app_dir = os.path.join(temp_dir, "app")
            write_generated_files(routes, app_dir)

            # Verify all files were created
            routes_dir = Path(app_dir) / "routes"
            assert (routes_dir / "index.tsx").exists()
            assert (routes_dir / "about.tsx").exists()
            assert (routes_dir / "interactive.tsx").exists()
            assert (Path(app_dir) / "routes.ts").exists()

            # Test home route (no components)
            home_content = (routes_dir / "index.tsx").read_text()
            assert "// No components needed for this route" in home_content
            assert (
                "const componentRegistry: Record<string, ComponentType<any>> = {};"
                in home_content
            )
            assert '"className": "home"' in home_content
            assert "Welcome to Pulse UI" in home_content

            # Test about route (with header/footer)
            about_content = (routes_dir / "about.tsx").read_text()
            assert 'import { Header } from "./components/Header";' in about_content
            assert 'import { Footer } from "./components/Footer";' in about_content
            assert '"header": Header,' in about_content
            assert '"footer": Footer,' in about_content
            assert '"tag": "$$header"' in about_content
            assert '"tag": "$$footer"' in about_content
            assert '"title": "About Page"' in about_content
            assert '"year": 2024' in about_content

            # Test interactive route (with buttons)
            interactive_content = (routes_dir / "interactive.tsx").read_text()
            assert (
                'import { Button } from "./components/Button";' in interactive_content
            )
            assert '"button": Button,' in interactive_content
            assert '"tag": "$$button"' in interactive_content
            assert '"variant": "primary"' in interactive_content
            assert '"size": "large"' in interactive_content

            # Test routes configuration
            config_content = (Path(app_dir) / "routes.ts").read_text()
            assert 'index("routes/index.tsx"),' in config_content
            assert 'route("/about", "routes/about.tsx"),' in config_content
            assert 'route("/interactive", "routes/interactive.tsx"),' in config_content

    def test_complex_nested_app(self):
        """Test generating an app with complex nested component structures."""
        self.setUp()

        # Define React components
        Layout = define_react_component("layout", "./Layout", "Layout", False)
        Card = define_react_component("card", "./Card", "Card", False)
        Counter = define_react_component("counter", "./Counter", "Counter", False)
        UserProfile = define_react_component(
            "user-profile", "./UserProfile", "UserProfile", False
        )

        @define_route(
            "/dashboard", components=["layout", "card", "counter", "user-profile"]
        )
        def dashboard_route():
            return Layout(title="Dashboard", sidebar=True)[
                div(className="dashboard-grid")[
                    Card(title="Welcome", variant="primary")[
                        h2()["Welcome Back!"],
                        p()["Here's your dashboard overview."],
                        UserProfile(
                            name="John Doe",
                            email="john@example.com",
                            avatar="/avatars/john.jpg",
                        ),
                    ],
                    Card(title="Statistics")[
                        h3()["Page Views"],
                        Counter(count=1234, label="Total Views")[
                            p()["Views this month"], strong()["↗️ +12% from last month"]
                        ],
                        Counter(count=89, label="Active Users"),
                    ],
                    Card(title="Recent Activity")[
                        ul()[
                            li()["User logged in - 2 minutes ago"],
                            li()["New post created - 15 minutes ago"],
                            li()["Profile updated - 1 hour ago"],
                        ]
                    ],
                ]
            ]

        routes = [dashboard_route]

        with tempfile.TemporaryDirectory() as temp_dir:
            app_dir = os.path.join(temp_dir, "app")
            write_generated_files(routes, app_dir)

            dashboard_content = (Path(app_dir) / "routes" / "dashboard.tsx").read_text()

            # Verify all components imported
            assert 'import { Layout } from "./Layout";' in dashboard_content
            assert 'import { Card } from "./Card";' in dashboard_content
            assert 'import { Counter } from "./Counter";' in dashboard_content
            assert 'import { UserProfile } from "./UserProfile";' in dashboard_content

            # Verify component registry
            assert '"layout": Layout,' in dashboard_content
            assert '"card": Card,' in dashboard_content
            assert '"counter": Counter,' in dashboard_content
            assert '"user-profile": UserProfile,' in dashboard_content

            # Verify nested structure in generated tree
            assert '"tag": "$$layout"' in dashboard_content
            assert '"tag": "$$card"' in dashboard_content
            assert '"tag": "$$counter"' in dashboard_content
            assert '"tag": "$$user-profile"' in dashboard_content

            # Verify props propagation
            assert '"title": "Dashboard"' in dashboard_content
            assert '"sidebar": true' in dashboard_content
            assert '"variant": "primary"' in dashboard_content
            assert '"name": "John Doe"' in dashboard_content
            assert '"count": 1234' in dashboard_content
            assert '"count": 89' in dashboard_content

    def test_dynamic_content_generation(self):
        """Test generating routes with dynamic Python content."""
        self.setUp()

        ListItem = define_react_component("list-item", "./ListItem", "ListItem", False)
        ProductCard = define_react_component(
            "product-card", "./ProductCard", "ProductCard", False
        )

        @define_route("/products", components=["list-item", "product-card"])
        def products_route():
            # Simulate fetching data
            categories = ["Electronics", "Clothing", "Books", "Home & Garden"]
            featured_products = [
                {"id": 1, "name": "Laptop", "price": 999, "rating": 4.5},
                {"id": 2, "name": "Smartphone", "price": 699, "rating": 4.2},
                {"id": 3, "name": "Headphones", "price": 199, "rating": 4.8},
            ]

            return div(className="products-page")[
                h1()["Our Products"],
                div(className="categories")[
                    h2()["Categories"],
                    ul()[
                        *[ListItem(key=cat, text=cat, icon="📁") for cat in categories]
                    ],
                ],
                div(className="featured")[
                    h2()["Featured Products"],
                    div(className="products-grid")[
                        *[
                            ProductCard(
                                key=str(product["id"]),
                                name=product["name"],
                                price=product["price"],
                                rating=product["rating"],
                            )[
                                p()[f"Product ID: {product['id']}"],
                                span()[f"⭐ {product['rating']}/5"],
                            ]
                            for product in featured_products
                        ]
                    ],
                ],
            ]

        routes = [products_route]

        with tempfile.TemporaryDirectory() as temp_dir:
            app_dir = os.path.join(temp_dir, "app")
            write_generated_files(routes, app_dir)

            products_content = (Path(app_dir) / "routes" / "products.tsx").read_text()

            # Verify dynamic list generation
            categories_found = products_content.count('"tag": "$$list-item"')
            assert categories_found == 4  # 4 categories

            products_found = products_content.count('"tag": "$$product-card"')
            assert products_found == 3  # 3 featured products

            # Verify dynamic content
            assert '"text": "Electronics"' in products_content
            assert '"text": "Clothing"' in products_content
            assert '"name": "Laptop"' in products_content
            assert '"price": 999' in products_content
            assert '"rating": 4.5' in products_content
            assert "Product ID: 1" in products_content
            assert "\\u2b50 4.8/5" in products_content


class TestComponentRegistryIntegration:
    """Test component registry integration across the system."""

    def setUp(self):
        """Clear the component registry before each test."""
        if hasattr(define_react_component, "_components"):
            define_react_component._components.clear()

    def test_component_registry_consistency(self):
        """Test that component registry is consistent across routes."""
        self.setUp()

        # Define components
        Header = define_react_component("header", "./Header", "Header", False)
        Button = define_react_component("button", "./Button", "Button", False)
        Card = define_react_component("card", "./Card", "Card", False)

        # Verify components are registered
        registry = get_registered_components()
        assert len(registry) == 3
        assert "header" in registry
        assert "button" in registry
        assert "card" in registry

        @define_route("/page1", components=["header", "button"])
        def page1():
            return div()[Header(), Button()]

        @define_route("/page2", components=["card", "button"])
        def page2():
            return div()[Card(), Button()]

        routes = [page1, page2]

        with tempfile.TemporaryDirectory() as temp_dir:
            app_dir = os.path.join(temp_dir, "app")
            write_generated_files(routes, app_dir)

            # Check page1 imports only needed components
            page1_content = (Path(app_dir) / "routes" / "page1.tsx").read_text()
            assert 'import { Header } from "./Header";' in page1_content
            assert 'import { Button } from "./Button";' in page1_content
            assert "import { Card }" not in page1_content  # Not used
            assert '"header": Header,' in page1_content
            assert '"button": Button,' in page1_content
            assert '"card"' not in page1_content  # Not in registry

            # Check page2 imports only needed components
            page2_content = (Path(app_dir) / "routes" / "page2.tsx").read_text()
            assert 'import { Card } from "./Card";' in page2_content
            assert 'import { Button } from "./Button";' in page2_content
            assert "import { Header }" not in page2_content  # Not used
            assert '"card": Card,' in page2_content
            assert '"button": Button,' in page2_content
            assert '"header"' not in page2_content  # Not in registry

    def test_component_props_serialization(self):
        """Test that component props are properly serialized."""
        self.setUp()

        DataComponent = define_react_component("data", "./Data", "Data", False)

        @define_route("/data-test", components=["data"])
        def data_route():
            return div()[
                DataComponent(
                    stringProp="hello world",
                    numberProp=42,
                    booleanProp=True,
                    nullProp=None,
                    arrayProp=[1, "two", True],
                    objectProp={"nested": {"deep": "value"}},
                    functionName="onClick",  # Should be treated as string
                )["Component with complex props"]
            ]

        routes = [data_route]

        with tempfile.TemporaryDirectory() as temp_dir:
            app_dir = os.path.join(temp_dir, "app")
            write_generated_files(routes, app_dir)

            content = (Path(app_dir) / "routes" / "data_test.tsx").read_text()

            # Verify proper JSON serialization
            assert '"stringProp": "hello world"' in content
            assert '"numberProp": 42' in content
            assert '"booleanProp": true' in content
            assert '"nullProp": null' in content
            # Array and object assertions need to account for pretty-printing
            assert '"arrayProp":' in content and '"two"' in content
            assert '"objectProp":' in content and '"deep": "value"' in content
            assert '"functionName": "onClick"' in content

            # Verify children
            assert '"Component with complex props"' in content


class TestErrorHandling:
    """Test error handling in the integration pipeline."""

    def setUp(self):
        """Clear the component registry before each test."""
        if hasattr(define_react_component, "_components"):
            define_react_component._components.clear()

    def test_missing_component_error(self):
        """Test error when route references non-existent component."""
        self.setUp()

        with pytest.raises(ValueError, match="Component 'nonexistent' not found"):

            @define_route("/bad-route", components=["nonexistent"])
            def bad_route():
                return div()["This should fail"]

    def test_partial_component_usage(self):
        """Test route that defines components but doesn't use all of them."""
        self.setUp()

        # This is actually allowed - route can define more components than it uses
        Button = define_react_component("button", "./Button", "Button", False)
        Modal = define_react_component("modal", "./Modal", "Modal", False)

        @define_route("/partial", components=["button", "modal"])
        def partial_route():
            return div()[
                h1()["Partial Usage"],
                Button()["Only button is used"],
                p()["Modal component is defined but not used"],
            ]

        routes = [partial_route]

        with tempfile.TemporaryDirectory() as temp_dir:
            app_dir = os.path.join(temp_dir, "app")
            write_generated_files(routes, app_dir)

            content = (Path(app_dir) / "routes" / "partial.tsx").read_text()

            # Both components should be imported and registered
            assert 'import { Button } from "./Button";' in content
            assert 'import { Modal } from "./Modal";' in content
            assert '"button": Button,' in content
            assert '"modal": Modal,' in content

            # But only button mount point should appear in tree
            assert '"tag": "$$button"' in content
            assert '"tag": "$$modal"' not in content


class TestRealWorldScenarios:
    """Test real-world usage scenarios."""

    def setUp(self):
        """Clear the component registry before each test."""
        if hasattr(define_react_component, "_components"):
            define_react_component._components.clear()

    def test_blog_app_scenario(self):
        """Test a realistic blog application scenario."""
        self.setUp()

        # Define blog-specific components
        BlogLayout = define_react_component(
            "blog-layout", "./components/BlogLayout", "BlogLayout", False
        )
        ArticleCard = define_react_component(
            "article-card", "./components/ArticleCard", "ArticleCard", False
        )
        CommentForm = define_react_component(
            "comment-form", "./components/CommentForm", "CommentForm", False
        )
        ShareButton = define_react_component(
            "share-button", "./components/ShareButton", "ShareButton", False
        )

        @define_route("/blog", components=["blog-layout", "article-card"])
        def blog_list():
            articles = [
                {
                    "id": 1,
                    "title": "Getting Started with Pulse UI",
                    "excerpt": "Learn the basics...",
                    "date": "2024-01-15",
                },
                {
                    "id": 2,
                    "title": "Advanced Component Patterns",
                    "excerpt": "Explore advanced...",
                    "date": "2024-01-10",
                },
            ]

            return BlogLayout(title="My Blog", showSidebar=True)[
                h1()["Latest Articles"],
                div(className="articles-grid")[
                    *[
                        ArticleCard(
                            id=article["id"],
                            title=article["title"],
                            excerpt=article["excerpt"],
                            publishedAt=article["date"],
                        )
                        for article in articles
                    ]
                ],
            ]

        @define_route(
            "/blog/:id", components=["blog-layout", "comment-form", "share-button"]
        )
        def blog_article():
            # Simulate article data
            return BlogLayout(title="Article Title", showSidebar=False)[
                article(className="blog-post")[
                    h1()["Getting Started with Pulse UI"],
                    p()["This is the article content..."],
                    p()["More content here..."],
                ],
                div(className="article-actions")[
                    ShareButton(url="/blog/1", title="Getting Started with Pulse UI"),
                    CommentForm(articleId=1, requireAuth=True),
                ],
            ]

        routes = [blog_list, blog_article]

        with tempfile.TemporaryDirectory() as temp_dir:
            app_dir = os.path.join(temp_dir, "app")
            write_generated_files(routes, app_dir)

            # Verify blog list route
            blog_content = (Path(app_dir) / "routes" / "blog.tsx").read_text()
            assert (
                'import { BlogLayout } from "./components/BlogLayout";' in blog_content
            )
            assert (
                'import { ArticleCard } from "./components/ArticleCard";'
                in blog_content
            )
            assert '"showSidebar": true' in blog_content
            assert '"title": "Getting Started with Pulse UI"' in blog_content

            # Verify article route
            article_content = (Path(app_dir) / "routes" / "blog_:id.tsx").read_text()
            assert (
                'import { CommentForm } from "./components/CommentForm";'
                in article_content
            )
            assert (
                'import { ShareButton } from "./components/ShareButton";'
                in article_content
            )
            assert '"requireAuth": true' in article_content
            assert '"articleId": 1' in article_content

            # Verify routes config
            config_content = (Path(app_dir) / "routes.ts").read_text()
            assert 'route("/blog", "routes/blog.tsx"),' in config_content
            assert 'route("/blog/:id", "routes/blog_:id.tsx"),' in config_content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
