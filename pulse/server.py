"""
WebSocket server for real-time UI updates.

This module provides the WebSocket server that maintains persistent connections
and handles UI tree updates from the Python backend to the React frontend.
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, Set
import websockets
from websockets.server import WebSocketServerProtocol

from .html import Route

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class UITreeServer:
    """
    WebSocket server for managing UI tree updates.
    
    Maintains persistent connections across routes and handles real-time updates.
    """
    
    def __init__(self, host: str = "localhost", port: int = 8080):
        self.host = host
        self.port = port
        self.clients: Set[WebSocketServerProtocol] = set()
        self.routes: Dict[str, Route] = {}
        
    def register_route(self, route: Route):
        """Register a route with the server."""
        self.routes[route.path] = route
        logger.info(f"Registered route: {route.path}")
    
    def register_routes(self, routes: List[Route]):
        """Register multiple routes with the server."""
        for route in routes:
            self.register_route(route)
    
    async def register_client(self, websocket: WebSocketServerProtocol):
        """Register a new WebSocket client."""
        self.clients.add(websocket)
        logger.info(f"Client connected. Total clients: {len(self.clients)}")
    
    async def unregister_client(self, websocket: WebSocketServerProtocol):
        """Unregister a WebSocket client."""
        self.clients.discard(websocket)
        logger.info(f"Client disconnected. Total clients: {len(self.clients)}")
    
    async def send_to_client(self, websocket: WebSocketServerProtocol, message: Dict):
        """Send a message to a specific client."""
        try:
            await websocket.send(json.dumps(message))
        except websockets.exceptions.ConnectionClosed:
            await self.unregister_client(websocket)
    
    async def broadcast(self, message: Dict):
        """Broadcast a message to all connected clients."""
        if not self.clients:
            return
        
        # Send to all clients, removing any that are disconnected
        disconnected = set()
        for client in self.clients:
            try:
                await client.send(json.dumps(message))
            except websockets.exceptions.ConnectionClosed:
                disconnected.add(client)
        
        # Clean up disconnected clients
        for client in disconnected:
            await self.unregister_client(client)
    
    async def send_ui_update(self, updates: List[Dict]):
        """Send UI tree updates to all clients."""
        message = {
            "type": "ui_updates",
            "updates": updates
        }
        await self.broadcast(message)
    
    async def send_full_tree(self, tree: Dict, route_path: Optional[str] = None):
        """Send a complete UI tree to clients."""
        message = {
            "type": "ui_tree",
            "tree": tree,
            "route": route_path
        }
        await self.broadcast(message)
    
    async def handle_client_message(self, websocket: WebSocketServerProtocol, message: str):
        """Handle incoming messages from clients."""
        try:
            data = json.loads(message)
            message_type = data.get("type")
            
            if message_type == "route_change":
                # Handle route change requests
                route_path = data.get("path")
                if route_path in self.routes:
                    route = self.routes[route_path]
                    # Re-render the route with current state
                    from .html import to_ui_tree
                    initial_element = route.render_func()
                    ui_tree = to_ui_tree(initial_element)
                    await self.send_to_client(websocket, {
                        "type": "ui_tree",
                        "tree": ui_tree,
                        "route": route_path
                    })
                else:
                    await self.send_to_client(websocket, {
                        "type": "error",
                        "message": f"Route not found: {route_path}"
                    })
            
            elif message_type == "ping":
                # Handle ping/pong for connection keep-alive
                await self.send_to_client(websocket, {"type": "pong"})
            
            else:
                logger.warning(f"Unknown message type: {message_type}")
                
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received: {message}")
        except Exception as e:
            logger.error(f"Error handling client message: {e}")
    
    async def handle_client(self, websocket: WebSocketServerProtocol, path: str):
        """Handle a WebSocket client connection."""
        await self.register_client(websocket)
        
        try:
            async for message in websocket:
                await self.handle_client_message(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            await self.unregister_client(websocket)
    
    async def start_server(self):
        """Start the WebSocket server."""
        logger.info(f"Starting WebSocket server on {self.host}:{self.port}")
        
        server = await websockets.serve(
            self.handle_client,
            self.host,
            self.port,
            ping_interval=20,
            ping_timeout=10
        )
        
        logger.info(f"WebSocket server running on ws://{self.host}:{self.port}")
        return server
    
    def run(self):
        """Run the server (blocking)."""
        asyncio.run(self._run_forever())
    
    async def _run_forever(self):
        """Internal method to run the server forever."""
        server = await self.start_server()
        await server.wait_closed()


# Global server instance
_server_instance: Optional[UITreeServer] = None


def get_server() -> UITreeServer:
    """Get the global server instance."""
    global _server_instance
    if _server_instance is None:
        _server_instance = UITreeServer()
    return _server_instance


def start_server(routes: List[Route], host: str = "localhost", port: int = 8080):
    """
    Start the WebSocket server with the given routes.
    
    Args:
        routes: List of Route objects to register
        host: Host to bind to
        port: Port to bind to
    """
    server = UITreeServer(host, port)
    server.register_routes(routes)
    server.run()


if __name__ == "__main__":
    # Example usage
    from .html import define_react_component, define_route, div, h1, p
    
    # Define some React components
    Counter = define_react_component("counter", "../ui-tree/demo-components", "Counter")
    
    # Define a route
    @define_route("/ws-example", components=["counter"])
    def ws_example_route():
        return div()[
            h1["WebSocket Example"],
            p["This route demonstrates WebSocket connectivity"],
            Counter(count=0, label="WebSocket Counter")
        ]
    
    # Start server
    start_server([ws_example_route])