import os
import duckdb
from dotenv import load_dotenv
import streamlit as st

# for use with local development credentials
load_dotenv()


def get_pg_dsn():
    """
    Construct a PostgreSQL DSN string from environment variables.
    """
    return (
        f"host={os.getenv('PG_HOST')} "
        f"port={os.getenv('PG_PORT')} "
        f"user={os.getenv('PG_USER')} "
        f"password={os.getenv('PG_PASSWORD')} "
        f"dbname={os.getenv('PG_DATABASE')}"
    )


def create_pg_connection():
    """
    Connect to a PostgreSQL database server using DuckDB.

    This function retrieves database credentials from os environment variables and uses them to establish
    a connection to the pgAdmin database.

    Returns:
        DuckDB connection object
    """
    conn = duckdb.connect()
    conn.execute("INSTALL postgres; LOAD postgres;")
    conn.execute("INSTALL spatial; LOAD spatial;")
    st.session_state["pg_connected"] = True
    return conn


def create_s3_connection(aws_region: str = "us-east-1"):
    """
    Create a connection to an S3 account using DuckDB.

    This function retrieves S3 credentials from environment variables and establishes a connection
    to an S3 account.

    Returns:
        DuckDB connection object
    """
    conn = duckdb.connect()
    conn.execute("INSTALL 'httpfs'")
    conn.execute("LOAD 'httpfs'")
    conn.execute(f"SET s3_region='{aws_region}'")
    st.session_state["s3_connected"] = True
    return conn
