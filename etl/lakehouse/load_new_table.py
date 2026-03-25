from connection import (
    connect_to_catalog,
    ensure_env_variables,
    load_project_config,
    postgres_connection_string,
    warehouse,
)
import pyarrow.parquet as pq
from dotenv import load_dotenv
from pyiceberg.schema import Schema
from pyiceberg.types import (
    BinaryType,
    BooleanType,
    DoubleType,
    LongType,
    NestedField,
    StringType,
    TimestampType,
)

import argparse
import logging
import os

logging.basicConfig(level=logging.INFO)

def table_props():
    """Table properties"""
    return {}


def from_parquet_schema(input_parquet_file: str):
    """Convert flattened GeoParquet schema to Iceberg schema"""
    parquet_table = pq.read_table(input_parquet_file)
    arrow_schema = parquet_table.schema

    def arrow_to_iceberg_type(arrow_type):
        """Convert PyArrow type to Iceberg type"""
        import pyarrow as pa

        # Handle struct types by converting to a string representation
        if isinstance(arrow_type, pa.StructType):
            # For struct types, store as string (JSON) to avoid complex nested reconstruction
            return StringType()

        type_str = str(arrow_type).lower()

        if "string" in type_str or "utf8" in type_str:
            return StringType()
        elif "int64" in type_str:
            return LongType()
        elif "int32" in type_str:
            return LongType()
        elif "double" in type_str or "float64" in type_str:
            return DoubleType()
        elif "float" in type_str or "float32" in type_str:
            return DoubleType()
        elif "bool" in type_str:
            return BooleanType()
        elif "binary" in type_str or "large_binary" in type_str:
            return BinaryType()
        elif "timestamp" in type_str:
            return TimestampType()
        elif "list" in type_str or "large_list" in type_str:
            # For list types, store as string
            return StringType()
        else:
            logging.warning(f"Unknown type {arrow_type}, defaulting to StringType")
            return StringType()

    # Build Iceberg schema from parquet columns
    # Keep dots in column names since they're struct columns that will be serialized
    fields = []
    for i, field in enumerate(arrow_schema):
        iceberg_type = arrow_to_iceberg_type(field.type)
        # Don't rename struct columns - they'll be serialized as JSON
        clean_name = field.name
        fields.append(
            NestedField(
                field_id=i + 1,
                name=clean_name,
                type=iceberg_type,
                required=not field.nullable,
            )
        )

    return Schema(fields=fields)


def new_stac_table(
    input_parquet_file: str,
    catalog,
    warehouse: str,
    table_name: str,
    table_name_space: str = "stac",
):
    """Create a new stac table and load data from parquet"""
    iceberg_table = f"{table_name_space}.{table_name}"

    s3_data_location = f"{warehouse}/{table_name_space}/{table_name}"

    # Read the parquet file to get its actual schema
    print(f"Reading parquet file schema from {input_parquet_file}...")
    parquet_table = pq.read_table(input_parquet_file)
    # if table_name == "fishnets":
    #     parquet_table = _prep_fishnets(input_parquet_file)
    # else:
    #     raise ValueError(f"Unsupported table name: {table_name}")
    print(f"Original parquet columns: {len(parquet_table.column_names)}")
    print(f"All column names: {parquet_table.column_names}")
    print(f"Column types: {[str(field.type) for field in parquet_table.schema]}")

    # Create schema from the renamed parquet table
    table_schema = from_parquet_schema(input_parquet_file)

    # Always drop existing table to ensure clean schema
    if catalog.table_exists(iceberg_table):
        print(f"Table `{iceberg_table}` already exists. Dropping...")
        catalog.drop_table(iceberg_table)
        print(f"Table `{iceberg_table}` dropped successfully.")

    # Create the Iceberg table with the parquet schema
    print(
        f"Creating table `{iceberg_table}` with {len(table_schema.columns)} columns..."
    )
    table = catalog.create_table(
        identifier=iceberg_table,
        schema=table_schema,
        location=s3_data_location,
        properties=table_props(),
    )
    print(f"Table `{iceberg_table}` has been created with schema:")
    for col in table_schema.columns:
        print(f"  - {col.name}: {col.field_type}")

    # Reload table reference to ensure we have the latest schema
    table = catalog.load_table(iceberg_table)

    # Append data to the Iceberg table
    print(f"Appending {len(parquet_table)} rows to `{iceberg_table}`...")
    print(f"Parquet table column names: {parquet_table.column_names}")
    print(f"Table schema column names: {[col.name for col in table.schema().columns]}")

    # Convert struct/list columns to JSON strings for Iceberg compatibility
    import json

    import pyarrow as pa

    df = parquet_table.to_pandas()

    def convert_to_json_string(x):
        """Convert any Python object to a valid JSON string."""
        if x is None:
            return None
        if isinstance(x, str):
            return x

        try:
            # First try to use json.dumps with a custom encoder for numpy types
            import numpy as np

            class NumpyEncoder(json.JSONEncoder):
                def default(self, obj):
                    if isinstance(obj, np.ndarray):
                        return obj.tolist()
                    elif isinstance(obj, np.integer):
                        return int(obj)
                    elif isinstance(obj, np.floating):
                        return float(obj)
                    elif isinstance(obj, (dict, list, tuple)):
                        return obj
                    else:
                        # For any other type, try to convert to native Python types
                        return str(obj)

            return json.dumps(x, cls=NumpyEncoder)
        except Exception as e:
            logging.warning(f"Failed to serialize to JSON: {e}, falling back to str()")
            return str(x)

    for col in df.columns:
        field_type = parquet_table.schema.field(col).type
        # Check if column needs conversion (struct or list types)
        if isinstance(field_type, (pa.StructType, pa.ListType)):
            print(f"Converting {col} from {field_type} to JSON string...")
            df[col] = df[col].apply(convert_to_json_string)

    # Build a schema that reflects the actual dataframe types
    schema_fields = []
    for field in parquet_table.schema:
        field_type = field.type
        # Convert struct/list types to string since we serialized them
        if isinstance(field_type, (pa.StructType, pa.ListType)):
            schema_fields.append(pa.field(field.name, pa.string()))
        elif isinstance(field_type, pa.TimestampType):
            # Force timestamp without timezone
            schema_fields.append(pa.field(field.name, pa.timestamp("us")))
        else:
            schema_fields.append(field)

    new_schema = pa.schema(schema_fields)

    # Convert back to PyArrow table with explicit schema
    parquet_table = pa.Table.from_pandas(df, schema=new_schema)

    table.append(parquet_table)
    print(f"Data loaded successfully. Total rows appended: {len(parquet_table)}")


def main(input_parquet_file: str, config: dict, table_name: str, table_name_space: str):
    catalog_root_path = warehouse(config["s3_bucket"], config["warehouse_prefix"])

    catalog = connect_to_catalog(
        pg_conn_string=postgres_connection_string(
            os.getenv("POSTGRES_HOST"),
            os.getenv("POSTGRES_PORT"),
            os.getenv("POSTGRES_USER"),
            os.getenv("POSTGRES_PASSWORD"),
            os.getenv("POSTGRES_DB"),
        ),
        catalog_name=config.get("catalog_name"),
        catalog_root=catalog_root_path,
        s3_access_key_id=os.getenv("S3_ACCESS_KEY_ID"),
        s3_secret_access_key=os.getenv("S3_SECRET_ACCESS_KEY"),
        s3_region=os.getenv("S3_REGION"),
    )

    # Create the stac table for STAC items
    new_stac_table(
        input_parquet_file,
        catalog,
        catalog_root_path,
        table_name=table_name,
        table_name_space=table_name_space,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create and load an Iceberg table from Parquet.")
    parser.add_argument("--project", required=True, help="Project name from projects.yaml (e.g. Trinity)")
    parser.add_argument("--config", default=None, help="Path to projects.yaml (default: auto-resolved)")
    parser.add_argument("--input", required=True, help="S3 path to the input Parquet file")
    parser.add_argument("--table-name", required=True, help="Name of the Iceberg table to create")
    parser.add_argument("--namespace", default="stac", help="Table namespace (default: stac)")
    args = parser.parse_args()

    load_dotenv(override=True)
    ensure_env_variables()
    kwargs = {"project_name": args.project}
    if args.config:
        kwargs["config_path"] = args.config
    config = load_project_config(**kwargs)
    main(args.input, config, table_name=args.table_name, table_name_space=args.namespace)
