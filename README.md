# db - Generic Database Module

A standalone, reusable database connection and session management module for SQLAlchemy async applications.

## Features

- **Async SQLAlchemy 2.0+**: Full async/await support
- **Connection Pooling**: Optimized AsyncPG connection pool
- **Session Management**: Context manager for automatic rollback/cleanup
- **Logging**: Configurable rich logging for development
- **Standalone**: No project-specific dependencies

## Installation

Add to your project's dependencies:

```toml
[project]
dependencies = ["db"]

[tool.uv.sources]
db = { workspace = true }
```

## Usage

### Basic Setup

```python
from db import Database, init_database, get_db

# Initialize with DATABASE_URL environment variable
db = init_database()

# Or with explicit URL
db = init_database('postgresql+asyncpg://user:pass@localhost/dbname')
```

## Configuration

The `Database` class accepts a `database_url` parameter. If not provided, it reads from the `DATABASE_URL` environment variable.

### Pool Settings (hardcoded defaults)

- `pool_size`: 15
- `max_overflow`: 10
- `pool_pre_ping`: True
- `pool_recycle`: 300 seconds
- `pool_timeout`: 30 seconds

## Project-Specific Models

This module is intentionally model-agnostic. For InterChat-specific models, see the `dbSupport` package in the workspace root which contains:

- SQLAlchemy model definitions
- Atlas migrations
- Schema configuration
