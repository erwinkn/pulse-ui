from ..react_component import ReactComponent

Link = ReactComponent("Link", "react-router", default_props={"prefetch": "intent"})
Outlet = ReactComponent("Outlet", "react-router")

__all__ = ["Link", "Outlet"]
