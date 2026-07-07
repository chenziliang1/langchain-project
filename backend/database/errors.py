"""
Database Error Handling Module

Provides MySQL error classification, specific exception types, and error handling utilities.
"""

from enum import Enum
from typing import Optional
import aiomysql


class DBErrorCode(Enum):
    """MySQL Common Error Code Classification"""
    # Connection errors
    CONNECTION_LOST = 2006          # MySQL server has gone away
    CONNECTION_TIMEOUT = 2013       # Lost connection during query
    CONNECTION_REFUSED = 2003       # Can't connect to MySQL server
    
    # Permission errors
    ACCESS_DENIED = 1045            # Access denied for user
    
    # Resource errors
    TOO_MANY_CONNECTIONS = 1040     # Too many connections
    OUT_OF_MEMORY = 1037            # Out of memory
    
    # Lock errors
    LOCK_WAIT_TIMEOUT = 1205        # Lock wait timeout exceeded
    DEADLOCK = 1213                 # Deadlock found
    
    # Query errors
    PARSE_ERROR = 1064              # SQL syntax error
    UNKNOWN_TABLE = 1109            # Unknown table
    UNKNOWN_COLUMN = 1054           # Unknown column
    DUPLICATE_ENTRY = 1062          # Duplicate entry


class DatabaseError(Exception):
    """
    Database Operation Exception Base Class
    
    Attributes:
        message: Error description
        error_code: MySQL error code
        original_error: Original exception object
    """
    def __init__(
        self, 
        message: str, 
        error_code: Optional[int] = None, 
        original_error: Optional[Exception] = None
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.original_error = original_error
    
    def __str__(self) -> str:
        if self.error_code:
            return f"[Error {self.error_code}] {self.message}"
        return self.message
    
    def is_retryable(self) -> bool:
        """Determine if this error can be resolved by retrying"""
        return False


class ConnectionLostError(DatabaseError):
    """Connection lost error (retryable)"""
    def is_retryable(self) -> bool:
        return True


class ConnectionTimeoutError(DatabaseError):
    """Connection timeout error (retryable)"""
    def is_retryable(self) -> bool:
        return True


class PoolExhaustedError(DatabaseError):
    """Connection pool exhausted error"""
    pass


class QueryTimeoutError(DatabaseError):
    """Query timeout/lock wait error"""
    def is_retryable(self) -> bool:
        # Lock wait can be retried
        if self.error_code == DBErrorCode.LOCK_WAIT_TIMEOUT.value:
            return True
        return False


class AuthenticationError(DatabaseError):
    """Database authentication failed"""
    pass


class QuerySyntaxError(DatabaseError):
    """SQL syntax error"""
    pass


class TableNotFoundError(DatabaseError):
    """Table does not exist"""
    pass


class ColumnNotFoundError(DatabaseError):
    """Column does not exist"""
    pass


def classify_mysql_error(error: aiomysql.Error) -> DatabaseError:
    """
    Classify MySQL error, convert to specific exception type
    
    Converts generic MySQL errors to specific exception types based on error code,
    allowing callers to handle different error types accordingly.
    
    Args:
        error: MySQL original error object
        
    Returns:
        DatabaseError: Classified specific exception
        
    Example:
        try:
            await cursor.execute("SELECT * FROM nonexistent")
        except aiomysql.Error as e:
            db_error = classify_mysql_error(e)
            if isinstance(db_error, TableNotFoundError):
                print(f"Table not found: {db_error}")
            elif db_error.is_retryable():
                print("Can retry")
    """
    # Extract error code and message
    error_code = None
    error_msg = str(error)
    
    # aiomysql.Error is usually a subclass of pymysql.err.MySQLError
    # Error code may be in args[0] or errno attribute
    if hasattr(error, 'args') and len(error.args) > 0:
        if isinstance(error.args[0], int):
            error_code = error.args[0]
    if error_code is None and hasattr(error, 'errno'):
        error_code = error.errno
    
    # Classify by error code
    # Connection errors (retryable)
    if error_code == DBErrorCode.CONNECTION_LOST.value:
        return ConnectionLostError(
            f"Database connection lost: {error_msg}",
            error_code=error_code,
            original_error=error
        )
    
    if error_code == DBErrorCode.CONNECTION_TIMEOUT.value:
        return ConnectionTimeoutError(
            f"Database connection timeout: {error_msg}",
            error_code=error_code,
            original_error=error
        )
    
    if error_code == DBErrorCode.CONNECTION_REFUSED.value:
        return ConnectionLostError(
            f"Cannot connect to database server: {error_msg}",
            error_code=error_code,
            original_error=error
        )
    
    # Authentication error
    if error_code == DBErrorCode.ACCESS_DENIED.value:
        return AuthenticationError(
            f"Database authentication failed: {error_msg}",
            error_code=error_code,
            original_error=error
        )
    
    # Resource errors
    if error_code == DBErrorCode.TOO_MANY_CONNECTIONS.value:
        return PoolExhaustedError(
            f"Too many database connections: {error_msg}",
            error_code=error_code,
            original_error=error
        )
    
    # Lock errors
    if error_code in [DBErrorCode.LOCK_WAIT_TIMEOUT.value, DBErrorCode.DEADLOCK.value]:
        return QueryTimeoutError(
            f"Query lock timeout: {error_msg}",
            error_code=error_code,
            original_error=error
        )
    
    # Syntax error
    if error_code == DBErrorCode.PARSE_ERROR.value:
        return QuerySyntaxError(
            f"SQL syntax error: {error_msg}",
            error_code=error_code,
            original_error=error
        )
    
    # Table not found
    if error_code == DBErrorCode.UNKNOWN_TABLE.value:
        return TableNotFoundError(
            f"Table not found: {error_msg}",
            error_code=error_code,
            original_error=error
        )
    
    # Column not found
    if error_code == DBErrorCode.UNKNOWN_COLUMN.value:
        return ColumnNotFoundError(
            f"Column not found: {error_msg}",
            error_code=error_code,
            original_error=error
        )
    
    # Other unknown errors
    return DatabaseError(
        f"Database error: {error_msg}",
        error_code=error_code,
        original_error=error
    )


# Export all content
__all__ = [
    # Error code enum
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
