"""
Async Database Connection Pool Management

Uses aiomysql to provide high-performance async MySQL connection pool.
"""

import os
import re
import asyncio
import logging
from typing import Optional, Any, Dict, List
from contextlib import asynccontextmanager

from dotenv import load_dotenv
import aiomysql

# Load .env file (if exists)
load_dotenv()
from aiomysql import Pool, Connection, Cursor

from .errors import (
    DatabaseError,
    ConnectionLostError,
    classify_mysql_error,
)

# Configure logging
logger = logging.getLogger("db_pool")


class DatabasePool:
    """
    Async Database Connection Pool Manager
    
    Singleton pattern ensures only one connection pool instance globally.
    Provides connection acquisition, query execution, transaction management, auto-retry, etc.
    
    Usage:
        # Initialize connection pool (at app startup)
        await DatabasePool.initialize()
        
        # Execute query (with auto-retry)
        pool = DatabasePool()
        results = await pool.fetchall("SELECT * FROM events_table LIMIT 10")
        
        # Use transaction
        async with pool.transaction() as conn:
            async with conn.cursor() as cur:
                await cur.execute("INSERT INTO ...")
        
        # Close connection pool
        await DatabasePool.close()
    """
    
    _instance: Optional["DatabasePool"] = None
    _lock: asyncio.Lock = asyncio.Lock()
    _pool: Optional[Pool] = None
    
    # Default connection pool configuration
    DEFAULT_CONFIG = {
        "host": os.getenv("DB_HOST", "db"),
        "port": int(os.getenv("DB_PORT", "3306")),
        "user": os.getenv("DB_USER", "root"),
        "password": os.getenv("DB_PASSWORD", "rootpassword"),
        "db": os.getenv("DB_NAME", "gdelt_db"),
        "charset": "utf8mb4",
        # Connection pool configuration
        "minsize": 1,
        "maxsize": 10,
        "autocommit": True,
        "connect_timeout": 30,
        # Connection recycle: recycle after 3600 seconds (1 hour) to prevent wait_timeout disconnect
        "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", "3600")),
    }
    
    # Retry configuration
    MAX_RETRIES = 3
    RETRY_DELAY = 0.5  # seconds
    
    def __new__(cls) -> "DatabasePool":
        """Singleton pattern"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    async def initialize(cls, **override_config) -> "DatabasePool":
        """
        Initialize connection pool
        
        Args:
            **override_config: Parameters to override default configuration
            
        Returns:
            DatabasePool: Connection pool instance
        """
        async with cls._lock:
            if cls._pool is None:
                config = {**cls.DEFAULT_CONFIG, **override_config}
                try:
                    cls._pool = await aiomysql.create_pool(**config)
                    logger.info(f"Connection pool initialized: {config['host']}:{config['port']}")
                    
                    # Test connection
                    async with cls._pool.acquire() as conn:
                        async with conn.cursor() as cur:
                            await cur.execute("SELECT 1")
                            await cur.fetchone()
                    logger.info("Connection pool test passed")
                    
                except Exception as e:
                    logger.error(f"Connection pool initialization failed: {e}")
                    raise ConnectionError(f"Database connection pool initialization failed: {e}")
        return cls()
    
    @classmethod
    async def close(cls) -> None:
        """Close connection pool"""
        async with cls._lock:
            if cls._pool is not None:
                cls._pool.close()
                await cls._pool.wait_closed()
                cls._pool = None
                cls._instance = None
                logger.info("Connection pool closed")
    
    @property
    def pool(self) -> Pool:
        """Get underlying connection pool"""
        if self._pool is None:
            raise RuntimeError("Connection pool not initialized, please call DatabasePool.initialize() first")
        return self._pool
    
    async def _execute_with_retry(
        self, 
        operation: callable,
        operation_name: str = "operation"
    ) -> Any:
        """
        Executor with retry mechanism
        
        Auto-retry for connection lost errors.
        
        Args:
            operation: Async operation function
            operation_name: Operation name (for logging)
            
        Returns:
            Operation result
            
        Raises:
            DatabaseError: Classified database exception
        """
        last_error = None
        
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                return await operation()
            except aiomysql.Error as e:
                db_error = classify_mysql_error(e)
                last_error = db_error
                
                # Only retry retryable errors
                if db_error.is_retryable() and attempt < self.MAX_RETRIES:
                    logger.warning(
                        f"{operation_name} failed (attempt {attempt}/{self.MAX_RETRIES}): "
                        f"{db_error.error_code} - {db_error}"
                    )
                    await asyncio.sleep(self.RETRY_DELAY * (2 ** (attempt - 1)))  # Exponential backoff
                    continue
                else:
                    # Non-retryable error or retries exhausted
                    raise db_error
            except DatabaseError:
                # Already classified error, re-raise
                raise
            except Exception:
                # Non-database errors, re-raise
                raise
        
        raise last_error
    
    @asynccontextmanager
    async def acquire(self) -> Connection:
        """
        Connection context manager (with health check)
        
        Usage:
            async with db_pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT 1")
        """
        conn = None
        pool = self._pool
        if pool is None:
            raise RuntimeError("Connection pool not initialized, please call DatabasePool.initialize() first")
        try:
            conn = await pool.acquire()
            
            # Simple health check: verify connection is available (async safe)
            try:
                await conn.ensure_connection()
            except Exception:
                pass  # ping failure is okay, aiomysql handles it automatically
            
            yield conn
        finally:
            if conn is not None:
                try:
                    pool.release(conn)
                except Exception:
                    pass
    
    @asynccontextmanager
    async def transaction(self) -> Connection:
        """
        Transaction context manager
        
        Auto handles commit and rollback.
        
        Usage:
            async with db_pool.transaction() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("INSERT INTO ...")
        """
        conn = None
        pool = self._pool
        if pool is None:
            raise RuntimeError("Connection pool not initialized, please call DatabasePool.initialize() first")
        try:
            conn = await pool.acquire()
            await conn.begin()
            yield conn
            await conn.commit()
            logger.debug("Transaction committed successfully")
        except Exception as e:
            if conn is not None:
                try:
                    await conn.rollback()
                except Exception:
                    pass
                logger.warning(f"Transaction rolled back: {e}")
            raise
        finally:
            if conn is not None:
                try:
                    pool.release(conn)
                except Exception:
                    pass
    
    async def fetchall(
        self, 
        query: str, 
        params: Optional[tuple] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute query, return all results (with retry)
        
        Args:
            query: SQL query statement
            params: Query parameters (prevent SQL injection)
            
        Returns:
            Result list, each row is a dictionary
            
        Raises:
            DatabaseError: Database error (classified)
        """
        async def _do_fetch():
            async with self.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(query, params)
                    return await cur.fetchall()
        
        return await self._execute_with_retry(_do_fetch, "fetchall")
    
    async def fetchone(
        self, 
        query: str, 
        params: Optional[tuple] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Execute query, return first result (with retry)
        
        Args:
            query: SQL query statement
            params: Query parameters
            
        Returns:
            Single row dictionary result, or None if not found
        """
        async def _do_fetch():
            async with self.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(query, params)
                    return await cur.fetchone()
        
        return await self._execute_with_retry(_do_fetch, "fetchone")
    
    async def execute(
        self, 
        query: str, 
        params: Optional[tuple] = None
    ) -> int:
        """
        Execute non-query statement (INSERT/UPDATE/DELETE, with retry)
        
        Args:
            query: SQL statement
            params: Query parameters
            
        Returns:
            Number of affected rows
        """
        async def _do_execute():
            async with self.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(query, params)
                    await conn.commit()
                    return cur.rowcount
        
        return await self._execute_with_retry(_do_execute, "execute")
    
    async def execute_many(
        self, 
        query: str, 
        params_list: List[tuple]
    ) -> int:
        """
        Batch execute same statement (with retry)
        
        Args:
            query: SQL statement
            params_list: Parameter list
            
        Returns:
            Number of affected rows
        """
        async def _do_execute_many():
            async with self.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.executemany(query, params_list)
                    await conn.commit()
                    return cur.rowcount
        
        return await self._execute_with_retry(_do_execute_many, "execute_many")
    
    def _sanitize_table_name(self, table_name: str) -> str:
        """
        Safely validate table name
        
        Only allows letters, numbers, underscores.
        
        Args:
            table_name: Original table name
            
        Returns:
            Validated table name
            
        Raises:
            ValueError: Invalid table name
        """
        if not table_name:
            raise ValueError("Table name cannot be empty")
        
        # Only allow letters, numbers, underscores
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table_name):
            raise ValueError(f"Invalid table name: {table_name} (only letters, numbers, underscores allowed)")
        
        return table_name
    
    async def get_schema(self, table_name: str = "events_table") -> List[Dict[str, Any]]:
        """
        Get table schema info (safe table name concatenation)
        
        Args:
            table_name: Table name
            
        Returns:
            Field info list
        """
        # Safely validate table name before concatenation (table names cannot be parameterized)
        safe_table_name = self._sanitize_table_name(table_name)
        query = f"DESCRIBE `{safe_table_name}`"
        
        return await self.fetchall(query)
    
    async def get_tables(self) -> List[str]:
        """
        Get all table names in database
        
        Returns:
            Table name list
        """
        result = await self.fetchall("SHOW TABLES")
        # Extract table name (first value of dictionary)
        tables = []
        for row in result:
            # SHOW TABLES returns column name as Tables_in_<dbname>
            table_name = list(row.values())[0]
            tables.append(table_name)
        return tables
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Detailed health check
        
        Returns:
            Health status dictionary
        """
        import time
        
        start_time = time.time()
        try:
            # Execute simple query test
            result = await self.fetchone("SELECT 1 as test, NOW() as server_time, CONNECTION_ID() as conn_id")
            latency_ms = round((time.time() - start_time) * 1000, 2)
            
            # Get connection pool status
            pool_size = self._pool.size if self._pool else 0
            free_connections = self._pool.freesize if self._pool else 0
            
            return {
                "status": "healthy",
                "latency_ms": latency_ms,
                "server_time": result.get("server_time") if result else None,
                "connection_id": result.get("conn_id") if result else None,
                "pool_size": pool_size,
                "free_connections": free_connections,
                "maxsize": self.DEFAULT_CONFIG.get("maxsize", 10),
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "latency_ms": round((time.time() - start_time) * 1000, 2),
            }


# Global connection pool instance reference
_db_pool: Optional[DatabasePool] = None
_db_pool_lock = asyncio.Lock()


async def get_db_pool() -> DatabasePool:
    """
    Get database connection pool instance
    
    If connection pool is not initialized, it will be auto-initialized.
    
    Returns:
        DatabasePool: Connection pool instance
    """
    global _db_pool
    if _db_pool is None:
        async with _db_pool_lock:
            if _db_pool is None:
                _db_pool = await DatabasePool.initialize()
    return _db_pool


async def close_db_pool() -> None:
    """Close global connection pool"""
    global _db_pool
    if _db_pool is not None:
        await DatabasePool.close()
        _db_pool = None
