# Database Infrastructure — Agent Context (`packages/db`)

This document is the specialized guide for agents working with the database infrastructure package (`packages/db`). It defines the connection engine, transaction scopes, connection pooling limits, and post-commit callback patterns.

---

## Package Structure

`packages/db` provides a reusable async database adapter wrapping SQLAlchemy:

```
packages/db/
├── src/
│   └── db/
│       ├── __init__.py   # Singleton accessor exports
│       ├── database.py   # Connection engine, pooling config, and UnitOfWork
│       └── logger.py     # Database logging helpers
└── pyproject.toml        # SQLAlchemy and asyncpg dependencies
```

---

## Connection Pooling Defaults

The database engine is created using `create_async_engine` with `asyncpg` as the driver. Pooling parameters are configured via environment variables with safety limits:

| Config Variable | Purpose | Fallback Default | Minimum Limit |
|---|---|---|---|
| `DB_POOL_SIZE` | Max number of persistent connections in the pool | `30` | `1` |
| `DB_MAX_OVERFLOW` | Max connections allowed beyond the pool size | `20` | `0` |
| `DB_POOL_TIMEOUT` | Seconds to wait for a connection before raising an error | `30` | `5` |
| `DB_POOL_RECYCLE` | Age in seconds after which a connection is closed and recreated | `300` | `30` |

- **Connection Health:** `pool_pre_ping=True` ensures stale/broken database connections are recycled before executing queries.
- **Connection LIFO:** `pool_use_lifo=True` uses the most recently returned connection to optimize backend connection state caching.

---

## Database Access Singletons

To avoid multiple connection pools, access the database through the global singletons exported in `db`:

```python
from db import init_database, get_db

# Initial setup (usually run in main.py lifespan)
db = init_database(database_url)

# Retrieve initialized instance in services/repositories
db = get_db()
```

---

## Transaction Lifecycles: `UnitOfWork`

The `UnitOfWork` class handles transactions by wrapping SQLAlchemy sessions and transactions:

### Basic Transaction
```python
db = get_db()
async with db.uow() as uow:
    # uow.session yields the AsyncSession
    await uow.session.execute(...)
# 1. If code exits cleanly: self._tx.commit() is executed
# 2. If an exception occurs: self._tx.rollback() is executed
# 3. Finally: self._session.close() is executed
```

### Post-Commit Callbacks (`on_commit`)
You can register asynchronous hooks to execute immediately after the database transaction successfully commits (e.g. queueing an outbox message, updating in-memory caches, or logging audit trails):

```python
async with db.uow() as uow:
    # 1. Do write operations
    await service.update_state(uow.session)
    
    # 2. Register post-commit callback
    uow.on_commit(lambda: notify_external_api(data))
    
# Callback executes sequentially AFTER successful transaction commit.
# If a callback fails, the error is logged, and subsequent callbacks continue executing.
```
