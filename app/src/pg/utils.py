import os
import sys
import psycopg2
import streamlit as st
from dotenv import load_dotenv

# for use with local development credentials
load_dotenv()


def create_database_connection():
    """
    Connect to a PostgreSQL database server using credentials from AWS Secrets Manager.

    This function retrieves database credentials from AWS Secrets Manager and uses them to establish
    a connection to the PostgreSQL database. It's designed to work with Streamlit applications.

    Returns:
        psycopg2.extensions.connection: A connection object representing the connection to the PostgreSQL server.

    Raises:
        psycopg2.Error: If an error occurs while establishing the connection.
        SystemExit: If a critical error occurs, triggering a system exit with status code 1.

    Note:
        This function uses st.error() to display errors in the Streamlit UI. Ensure that this function
        is called within a Streamlit app context.
    """
    try:
        # Create connection dictionary
        p_connection_dictionary = {
            "host": os.getenv("PG_HOST"),
            "database": os.getenv("PG_DATABASE"),
            "user": os.getenv("PG_USER"),
            "password": os.getenv("PG_PASSWORD"),
            "port": os.getenv("PG_PORT")
        }

        # Connect to the PostgreSQL server
        print("Connecting to the PostgreSQL database...")
        conn = psycopg2.connect(**p_connection_dictionary)
        print("Connection Succeeded!")
    except (Exception, psycopg2.DatabaseError) as error:
        # Log the error and display it in the Streamlit UI
        print(f"Error: {error}", file=sys.stderr)
        st.error(f"Database connection error: {error}")
        sys.exit(1)
    return conn


def connect_to_db():
    """
    Connect to the database and set up Streamlit session state.

    This function establishes a database connection using create_database_connection()
    and sets up Streamlit session state variables to manage the connection status.

    It sets the following Streamlit session state variables:
    - db_connected (bool): Indicates whether the database connection was successful.
    - conn (psycopg2.extensions.connection): The database connection object.

    Returns:
        None

    Note:
        This function is designed to be used within a Streamlit application. It modifies
        the Streamlit session state, which should only be done in the context of a Streamlit app.
    """
    # Connect to the database
    p_conn = create_database_connection()
    p_conn.autocommit = True

    # Set Streamlit session state variables
    st.session_state["db_connected"] = True
    st.session_state["db_conn"] = p_conn
