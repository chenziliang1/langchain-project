"""
Streaming Query Module

Provides generator-style streaming queries, memory-friendly for large data volumes.
Supports backpressure control and timeout control.
"""

import asyncio
import logging
from typing import AsyncGenerator, Optional, Any, Callable
from contextlib import asynccontextmanager

import aiomysql

from .pool import DatabasePool

logger = logging.getLogger("streaming")


class StreamingQuery:
    """
    Streaming Query Executor
    
    Uses MySQL Cursor's SSCursor (Server Side Cursor) for true streaming reads,
    returning data in chunks to avoid loading all into memory at once.
    
    Usage:
        async for row in StreamingQuery(pool).stream("SELECT * FROM big_table"):
            process(row)
    """
    
    def __init__(
        self, 
        pool: DatabasePool,
        chunk_size: int = 100,
        timeout: float = 30.0
    ):
        self.pool = pool
        self.chunk_size = chunk_size
        self.timeout = timeout
    
    async def stream(
        self,
        query: str,
        params: Optional[tuple] = None
    ) -> AsyncGenerator[dict, None]:
        """
        Streaming query - generator returns results
        
        Args:
            query: SQL query
            params: Parameters
            chunk_size: Number of rows to fetch each time
            
        Yields:
            Single row data (dictionary format)
        """
        conn = None
        pool = self.pool._pool
        if pool is None:
            raise RuntimeError("Connection pool not initialized")
        try:
            # Get regular connection (SSCursor needs special handling)
            conn = await pool.acquire()
            
            # Use SSDictCursor server-side cursor
            async with conn.cursor(aiomysql.SSDictCursor) as cur:
                # Set read timeout
                await cur.execute("SET SESSION net_read_timeout = %s", (int(self.timeout),))
                
                # Execute query
                await asyncio.wait_for(
                    cur.execute(query, params),
                    timeout=self.timeout
                )
                
                row_count = 0
                while True:
                    # Read in batches
                    rows = await asyncio.wait_for(
                        cur.fetchmany(self.chunk_size),
                        timeout=self.timeout
                    )
                    if not rows:
                        break
                    
                    for row in rows:
                        row_count += 1
                        yield row
                
                logger.debug(f"Streaming query complete: {row_count} rows")
                
        except asyncio.TimeoutError:
            logger.error(f"Streaming query timeout: {self.timeout}s")
            raise
        finally:
            if conn is not None:
                try:
                    pool.release(conn)
                except Exception:
                    pass
    
    async def stream_with_transform(
        self,
        query: str,
        transform: Callable[[dict], Any],
        params: Optional[tuple] = None
    ) -> AsyncGenerator[Any, None]:
        """
        Streaming query + real-time transform
        
        Perform data transformation while streaming reads to reduce memory usage.
        """
        async for row in self.stream(query, params):
            yield transform(row)
    
    async def count(self, query: str, params: Optional[tuple] = None) -> int:
        """
        Stream count - without loading all data
        """
        count = 0
        async for _ in self.stream(query, params):
            count += 1
        return count
    
    async def to_list(
        self,
        query: str,
        params: Optional[tuple] = None,
        limit: int = 10000
    ) -> list[dict]:
        """
        Stream to list (with limit protection)
        """
        results = []
        async for row in self.stream(query, params):
            results.append(row)
            if len(results) >= limit:
                logger.warning(f"Reached limit {limit}, truncating results")
                break
        return results


class ParallelQuery:
    """
    Parallel Query Executor
    
    Execute multiple independent queries concurrently, total time = slowest query time.
    """
    
    def __init__(self, pool: DatabasePool, max_concurrent: int = 5):
        self.pool = pool
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
    
    async def execute_single(
        self,
        query: str,
        params: Optional[tuple] = None,
        query_name: str = ""
    ) -> dict:
        """Execute single query (with semaphore concurrency control)"""
        async with self.semaphore:
            start = asyncio.get_event_loop().time()
            try:
                rows = await self.pool.fetchall(query, params)
                elapsed = asyncio.get_event_loop().time() - start
                return {
                    "name": query_name,
                    "rows": rows,
                    "count": len(rows),
                    "elapsed_ms": round(elapsed * 1000, 2),
                    "error": None
                }
            except Exception as e:
                elapsed = asyncio.get_event_loop().time() - start
                return {
                    "name": query_name,
                    "rows": [],
                    "count": 0,
                    "elapsed_ms": round(elapsed * 1000, 2),
                    "error": str(e)
                }
    
    async def execute_many(
        self,
        queries: list[tuple[str, Optional[tuple], str]]
    ) -> list[dict]:
        """
        Execute multiple queries concurrently
        
        Args:
            queries: [(query, params, name), ...]
            
        Returns:
            Result list for each query
        """
        tasks = [
            self.execute_single(query, params, name)
            for query, params, name in queries
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle exceptions
        processed = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed.append({
                    "name": queries[i][2],
                    "rows": [],
                    "count": 0,
                    "elapsed_ms": 0,
                    "error": str(result)
                })
            else:
                processed.append(result)
        
        return processed


class BatchedInserter:
    """
    Batch Insert Optimizer
    
    Automatically batch inserts to avoid single-insert performance issues.
    """
    
    def __init__(self, pool: DatabasePool, batch_size: int = 1000):
        self.pool = pool
        self.batch_size = batch_size
        self.buffer = []
    
    async def add(self, record: dict) -> None:
        """Add record to buffer"""
        self.buffer.append(record)
        
        if len(self.buffer) >= self.batch_size:
            await self.flush()
    
    async def flush(self) -> int:
        """Write buffer to database"""
        if not self.buffer:
            return 0
        
        # Build batch insert SQL
        columns = list(self.buffer[0].keys())
        placeholders = ', '.join(['%s'] * len(columns))
        columns_str = ', '.join([f"`{c}`" for c in columns])
        
        query = f"INSERT INTO events_table ({columns_str}) VALUES ({placeholders})"
        
        # Extract values
        values = [
            tuple(record.get(c) for c in columns)
            for record in self.buffer
        ]
        
        # Use executemany
        affected = await self.pool.execute_many(query, values)
        
        count = len(self.buffer)
        self.buffer.clear()
        
        logger.debug(f"Batch insert: {count} records")
        return affected
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.flush()


# Convenience functions
async def stream_query(
    query: str,
    params: Optional[tuple] = None,
    chunk_size: int = 100,
    timeout: float = 30.0
) -> AsyncGenerator[dict, None]:
    """
    Convenience function: streaming query
    """
    pool = await get_db_pool()
    streamer = StreamingQuery(pool, chunk_size, timeout)
    async for row in streamer.stream(query, params):
        yield row


async def parallel_queries(
    queries: list[tuple[str, Optional[tuple], str]],
    max_concurrent: int = 5
) -> list[dict]:
    """
    Convenience function: parallel query
    
    Args:
        queries: [(sql, params, name), ...]
        max_concurrent: Maximum concurrency
        
    Returns:
        Query result list
        
    Example:
        results = await parallel_queries([
            ("SELECT COUNT(*) FROM events WHERE SQLDATE='2024-01-01'", None, "jan1_count"),
            ("SELECT COUNT(*) FROM events WHERE SQLDATE='2024-01-02'", None, "jan2_count"),
        ])
    """
    pool = await get_db_pool()
    executor = ParallelQuery(pool, max_concurrent)
    return await executor.execute_many(queries)
