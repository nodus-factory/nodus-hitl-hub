"""Database queries and connection management."""

import logging
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def create_pool(dsn: str, min_size: int = 2, max_size: int = 10) -> asyncpg.Pool:
    """Create an asyncpg connection pool."""
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=dsn,
        min_size=min_size,
        max_size=max_size,
        command_timeout=30,
    )
    logger.info("Database pool created (min=%d max=%d)", min_size, max_size)
    return _pool


async def get_pool() -> asyncpg.Pool:
    """Get the global connection pool."""
    if _pool is None:
        raise RuntimeError("Database pool not initialized. Call create_pool() first.")
    return _pool


async def close_pool() -> None:
    """Close the connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("Database pool closed")


async def run_migrations(pool: asyncpg.Pool, migrations_dir: str) -> None:
    """Run SQL migrations from a directory (idempotent via IF NOT EXISTS)."""
    import os

    async with pool.acquire() as conn:
        files = sorted(f for f in os.listdir(migrations_dir) if f.endswith(".sql"))
        for filename in files:
            path = os.path.join(migrations_dir, filename)
            with open(path) as f:
                sql = f.read()
            try:
                await conn.execute(sql)
                logger.info("Migration applied: %s", filename)
            except Exception as e:
                logger.error("Migration failed: %s — %s", filename, e)
                raise
