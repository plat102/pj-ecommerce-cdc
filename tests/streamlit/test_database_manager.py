"""Happy-path tests for DatabaseManager.

DatabaseManager wraps psycopg2 and calls streamlit.st.error on exceptions;
both are mocked so tests run without a live Postgres or Streamlit runtime.
"""
import pandas as pd

from managers.database import DatabaseManager


def test_execute_query_calls_cursor_execute_with_sql(mock_psycopg2_connect, mocker):
    mocker.patch("managers.database.st")  # silence st.error
    cursor = mock_psycopg2_connect.cursor.return_value
    cursor.description = [("id",), ("email",)]
    cursor.fetchall.return_value = [(1, "a@b.c")]

    db = DatabaseManager({"host": "x", "user": "u", "password": "p", "dbname": "d"})
    result = db.execute_query("SELECT id, email FROM customers")

    cursor.execute.assert_called_once_with("SELECT id, email FROM customers", None)
    assert isinstance(result, pd.DataFrame)
    assert list(result.columns) == ["id", "email"]
    assert result.iloc[0]["id"] == 1


def test_execute_query_with_params_forwards_params(mock_psycopg2_connect, mocker):
    mocker.patch("managers.database.st")
    cursor = mock_psycopg2_connect.cursor.return_value
    cursor.description = [("count",)]
    cursor.fetchall.return_value = [(5,)]

    db = DatabaseManager({"host": "x"})
    db.execute_query("SELECT COUNT(*) FROM customers WHERE id > %s", params=(10,))

    cursor.execute.assert_called_once_with(
        "SELECT COUNT(*) FROM customers WHERE id > %s", (10,)
    )


def test_execute_query_no_fetch_commits(mock_psycopg2_connect, mocker):
    mocker.patch("managers.database.st")
    db = DatabaseManager({"host": "x"})
    result = db.execute_query("INSERT INTO t VALUES (1)", fetch=False)

    assert result is True
    mock_psycopg2_connect.commit.assert_called_once()
