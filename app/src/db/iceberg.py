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

    This function uses the AWS extension with credential_chain provider to automatically
    fetch credentials using AWS SDK default provider chain, supporting ECS instance credentials.

    Returns:
        DuckDB connection object
    """
    conn = duckdb.connect()
    conn.execute("INSTALL 'aws'")
    conn.execute("LOAD 'aws'")
    conn.execute("INSTALL 'httpfs'")
    conn.execute("LOAD 'httpfs'")
    conn.execute("INSTALL 'iceberg'")
    conn.execute("LOAD 'iceberg'")

    # Create S3 secret using credential_chain provider for automatic credential detection
    conn.execute(f"""
        CREATE OR REPLACE SECRET aws_secret (
            TYPE s3,
            PROVIDER credential_chain,
            REGION '{aws_region}'
        )
    """)
    st.session_state["s3_connected"] = True
    return conn


def create_and_load_iceberg_table(
    conn: duckdb.DuckDBPyConnection,
    table_name: str,
    parquet_files: list[str],
    catalog_path: str,
    schema: str = None,
    union_by_name: bool = False
):
    """
    Create an Iceberg table and load data from a list of parquet files.
    
    Note: DuckDB's Iceberg extension currently works with REST catalogs (Iceberg REST Catalog servers).
    For S3-based catalogs, you need to either:
    1. Use a REST catalog service (like Apache Iceberg REST)
    2. Read Iceberg tables directly using iceberg_scan()
    3. Create regular DuckDB tables instead
    
    This function creates a regular DuckDB table from parquet files.
    
    Args:
        conn: DuckDB connection object with Iceberg extension loaded
        table_name: Name of the table to create
        parquet_files: List of S3 paths or local paths to parquet files
        catalog_path: Not used in current implementation (kept for API compatibility)
        schema: Optional SQL schema definition (e.g., "id INT, name VARCHAR")
                If None, schema is inferred from the first parquet file
        union_by_name: If True, uses UNION BY NAME to combine files with different schemas,
                      filling missing columns with NULL. If False (default), requires all
                      files to have the same schema.
    
    Returns:
        pd.DataFrame: The created table as a pandas DataFrame
    
    Example:
        df = create_and_load_iceberg_table(
            conn,
            "my_table",
            ["s3://bucket/data1.parquet", "s3://bucket/data2.parquet"],
            None,  # catalog_path not used for now
            union_by_name=True  # Use this if files have different schemas
        )
    """
    # Ensure Iceberg extension is loaded
    conn.execute("LOAD 'iceberg'")
    
    if union_by_name:
        # Create table by reading all parquet files with UNION BY NAME
        # This allows files with different schemas to be combined
        parquet_list = "', '".join(parquet_files)
        conn.execute(f"""
            CREATE OR REPLACE TABLE {table_name} AS 
            SELECT * FROM read_parquet(['{parquet_list}'], union_by_name=true)
        """)
        print(f"Successfully created table '{table_name}' from {len(parquet_files)} parquet file(s) using UNION BY NAME")
    else:
        # Create table from first parquet file
        conn.execute(f"""
            CREATE OR REPLACE TABLE {table_name} AS 
            SELECT * FROM read_parquet('{parquet_files[0]}')
        """)
        
        # Insert data from remaining parquet files
        for parquet_file in parquet_files[1:]:
            conn.execute(f"""
                INSERT INTO {table_name}
                SELECT * FROM read_parquet('{parquet_file}')
            """)
        
        print(f"Successfully created table '{table_name}' and loaded {len(parquet_files)} parquet file(s)")
    
    # Get row count and column info
    row_count = conn.execute(f'SELECT COUNT(*) FROM {table_name}').fetchone()[0]
    print(f"Table rows: {row_count}")
    
    # Convert table to DataFrame and return
    df = conn.execute(f'SELECT * FROM {table_name}').df()
    print(f"Returning DataFrame with shape: {df.shape}")
    
    return df


def create_table_from_iceberg_metadata(
    conn: duckdb.DuckDBPyConnection,
    table_name: str,
    metadata_json_path: str
):
    """
    Create a table by reading an Iceberg metadata JSON file from S3.
    
    This function uses DuckDB's iceberg_scan() to read Iceberg table metadata
    and create a table from the referenced data files.
    
    Args:
        conn: DuckDB connection object with S3 and Iceberg extensions loaded
        table_name: Name of the table to create
        metadata_json_path: S3 path to the Iceberg metadata JSON file
                           (e.g., 's3://bucket/path/metadata/v1.metadata.json')
    
    Returns:
        pd.DataFrame: The created table as a pandas DataFrame
    
    Example:
        df = create_table_from_iceberg_metadata(
            conn,
            "my_iceberg_table",
            "s3://bucket/warehouse/db/table/metadata/v1.metadata.json"
        )
    """
    # Create table using iceberg_scan to read from metadata
    conn.execute(f"""
        CREATE OR REPLACE TABLE {table_name} AS 
        SELECT * FROM iceberg_scan('{metadata_json_path}')
    """)
    
    row_count = conn.execute(f'SELECT COUNT(*) FROM {table_name}').fetchone()[0]
    print(f"Successfully created table '{table_name}' from Iceberg metadata")
    print(f"Table rows: {row_count}")
    
    # Display schema
    schema = conn.execute(f'DESCRIBE {table_name}').fetchall()
    print(f"Table schema ({len(schema)} columns):")
    for col in schema[:5]:  # Show first 5 columns
        print(f"  - {col[0]}: {col[1]}")
    if len(schema) > 5:
        print(f"  ... and {len(schema) - 5} more columns")
    
    # Convert table to DataFrame and return
    df = conn.execute(f'SELECT * FROM {table_name}').df()
    print(f"Returning DataFrame with shape: {df.shape}")
    
    return df


if __name__ == "__main__":
    catalog = "s3://trinity-pilot/dev/conformance/iceberg-warehouse/hydraulics/job_metadata/metadata/"
    conn = create_s3_connection()

    # create_and_load_iceberg_table(
    #     conn,
    #     "test_table",
    #     ["s3://trinity-pilot/dev/conformance/simulations/event-data/11/hydraulics/bardwell-creek/flow_timeseries.pq",
    #      "s3://trinity-pilot/dev/conformance/simulations/event-data/11/hydraulics/bedias-creek/flow_timeseries.pq"],
    #     catalog,
    #     union_by_name=True  # Files have different schemas, so use UNION BY NAME
    # )

    df = create_table_from_iceberg_metadata(
        conn,
        "test_table",
        "s3://trinity-pilot/dev/conformance/iceberg-warehouse/hydraulics/flow_timeseries/metadata/00000-f0bbe3d2-4674-47e0-84af-5dd044f7ec2f.metadata.json",
    )
    
    print("\nDataFrame info:")
    print(df.head())

