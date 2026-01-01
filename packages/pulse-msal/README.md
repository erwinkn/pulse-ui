# Pulse MSAL

Microsoft Entra ID (Azure AD) authentication plugin for Pulse applications using MSAL.

## Architecture

Server-side OAuth2 authentication using Microsoft Authentication Library (MSAL). Handles token acquisition, caching, and session management.

```
┌──────────────────────────────────────────────────────────────────┐
│  Pulse App                                                       │
│  ┌────────────────┐  ┌─────────────────┐  ┌──────────────────┐  │
│  │   MSALPlugin   │──│ TokenCacheStore │──│ UserSession      │  │
│  └────────────────┘  └─────────────────┘  └──────────────────┘  │
│          │                                                       │
│          │ OAuth2 Auth Code Flow                                 │
│          ▼                                                       │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │              Microsoft Entra ID                             │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

## Folder Structure

```
src/pulse_msal/
├── __init__.py    # Public exports
└── plugin.py      # MSALPlugin, TokenCacheStore, auth helpers
```

## Usage

### Setup

```python
import pulse as ps
from pulse_msal import MSALPlugin, FileTokenCacheStore

app = ps.App(
    plugins=[
        MSALPlugin(
            client_id="your-client-id",
            client_secret="your-client-secret",
            tenant_id="your-tenant-id",
            redirect_uri="http://localhost:8000/auth/callback",
            scopes=["User.Read"],
            token_cache_store=FileTokenCacheStore(".token_cache"),
        ),
    ],
    routes=[...],
)
```

### Authentication Functions

```python
from pulse_msal import auth, login, logout

@ps.component
def protected_page():
    user = auth()
    if not user:
        return ps.button("Login", onClick=lambda _: login())

    return ps.div([
        ps.p(f"Hello, {user['name']}"),
        ps.button("Logout", onClick=lambda _: logout()),
    ])
```

### Claims Mapping

Custom claims extraction:

```python
from pulse_msal import MSALPlugin, ClaimsMapper

def custom_mapper(claims: dict) -> dict:
    return {
        "id": claims.get("oid"),
        "email": claims.get("preferred_username"),
        "name": claims.get("name"),
        "roles": claims.get("roles", []),
    }

MSALPlugin(
    ...,
    claims_mapper=custom_mapper,
)
```

## Token Cache Stores

### FileTokenCacheStore

File-based token caching for development:

```python
from pulse_msal import FileTokenCacheStore

FileTokenCacheStore(cache_dir=".token_cache")
```

### RedisTokenCacheStore

Redis-backed caching for production:

```python
from pulse_msal import RedisTokenCacheStore

RedisTokenCacheStore(
    redis_url="redis://localhost:6379",
    prefix="msal:",
)
```

### Custom Store

Implement the `TokenCacheStore` protocol:

```python
from pulse_msal import TokenCacheStore

class CustomStore(TokenCacheStore):
    async def get(self, key: str) -> bytes | None: ...
    async def set(self, key: str, value: bytes) -> None: ...
    async def delete(self, key: str) -> None: ...
```

## Main Exports

- `MSALPlugin` - authentication plugin
- `TokenCacheStore` - cache protocol
- `FileTokenCacheStore` - file-based cache
- `RedisTokenCacheStore` - Redis cache
- `ClaimsMapper` - claims transformation type
- `auth()` - get current user
- `login()` - initiate login flow
- `logout()` - clear session
