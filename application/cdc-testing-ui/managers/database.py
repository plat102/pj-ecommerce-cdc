"""
Database Manager for handling PostgreSQL operations
"""
import psycopg2
import pandas as pd
import streamlit as st
from typing import Dict


class DatabaseManager:
    """Handle database operations"""

    def __init__(self, config: Dict):
        self.config = config
        self._connection = None

    @property
    def connection(self):
        if self._connection is None or self._connection.closed:
            self._connection = psycopg2.connect(**self.config)
        return self._connection

    def execute_query(self, query: str, params=None, fetch=True):
        """Execute SQL query"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, params)
                if fetch:
                    columns = (
                        [desc[0] for desc in cursor.description]
                        if cursor.description
                        else []
                    )
                    rows = cursor.fetchall()
                    return (
                        pd.DataFrame(rows, columns=columns) if rows else pd.DataFrame()
                    )
                else:
                    self.connection.commit()
                    return True
        except Exception as e:
            self.connection.rollback()
            st.error(f"Database error: {e}")
            return None

    def get_table_data(self, table: str) -> pd.DataFrame:
        """Get all data from a table"""
        query = f"SELECT * FROM {table} ORDER BY id"
        return self.execute_query(query)

    def get_table_count(self, table: str) -> int:
        """Get row count for a table"""
        query = f"SELECT COUNT(*) as count FROM {table}"
        result = self.execute_query(query)
        return result.iloc[0]["count"] if not result.empty else 0

    def test_connection(self) -> bool:
        """Test database connection"""
        try:
            self.execute_query("SELECT 1")
            return True
        except Exception:
            return False

    def test_connection(self) -> bool:
        """Test database connection"""
        try:
            self.execute_query("SELECT 1")
            return True
        except Exception:
            return False