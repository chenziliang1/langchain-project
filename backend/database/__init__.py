"""
Async Database Connection Pool Module

Provides unified async database connection pool management and query execution interface.
"""

from .pool import DatabasePool, get_db_pool, close_db_pool
from .errors import (
    # Error codes
    DBErrorCode,
    # Exception classes
    DatabaseError,
    ConnectionLostError,
    ConnectionTimeoutError,
    PoolExhaustedError,
    QueryTimeoutError,
    AuthenticationError,
    QuerySyntaxError,
    TableNotFoundError,
    ColumnNotFoundError,
    # Functions
    classify_mysql_error,
)

__all__ = [
    # Connection pool
    "DatabasePool",
    "get_db_pool",
    "close_db_pool",
    # Error codes
    "DBErrorCode",
    # Exception classes
    "DatabaseError",
    "ConnectionLostError",
    "ConnectionTimeoutError",
    "PoolExhaustedError",
    "QueryTimeoutError",
    "AuthenticationError",
    "QuerySyntaxError",
    "TableNotFoundError",
    "ColumnNotFoundError",
    # Functions
    "classify_mysql_error",
]
