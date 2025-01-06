from constructs import Construct
from cdktf_cdktf_provider_postgresql.provider import PostgresqlProvider
from cdktf_cdktf_provider_postgresql.database import Database
from cdktf_cdktf_provider_postgresql.role import Role


class PostgresInitConstruct(Construct):
    """
    A Construct for initializing PostgreSQL databases and roles.

    This construct manages the creation of PostgreSQL databases and roles required
    for applications like Keycloak. It sets up the necessary database objects
    after the RDS instance is provisioned.

    Attributes:
        keycloak_database (Database): The Keycloak application database.
        keycloak_role (Role): The database role for Keycloak access.
        streamlit_database (Database): The Streamlit application database.
        streamlit_role (Role): The database role for Streamlit access.

    Parameters:
        scope (Construct): The scope in which this construct is defined.
        id (str): The unique identifier of the construct.
        host (str): The RDS instance endpoint.
        port (int): The PostgreSQL port number.
        superuser (str): The superuser username.
        superuser_password (str): The superuser password.
        keycloak_password (str): The password for Keycloak database user.
        streamlit_password (str): The password for Streamlit database user.

    Methods:
        __init__(self, scope, id, ...): Initializes the PostgreSQL databases and roles.
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        host: str,
        port: int,
        superuser: str,
        superuser_password: str,
        keycloak_password: str,
        streamlit_password: str,
    ) -> None:
        super().__init__(scope, id)

        # Configure PostgreSQL Provider
        PostgresqlProvider(
            self,
            "postgresql",
            host=host,
            port=port,
            username=superuser,
            password=superuser_password,
            sslmode="require",
            connect_timeout=60,
            max_connections=5,
            superuser=False,
            expected_version="15.5",
        )

        # Create Keycloak Role
        self.keycloak_role = Role(
            self,
            "keycloak-role",
            name="keycloak",
            login=True,
            password=keycloak_password,
            connection_limit=-1,  # Unlimited connections
        )

        # Create Keycloak Database
        self.keycloak_database = Database(
            self,
            "keycloak-db",
            name="keycloak",
            owner=self.keycloak_role.name,
            connection_limit=-1,
            allow_connections=True,
        )

        # Create Streamlit Role
        self.streamlit_role = Role(
            self,
            "streamlit-role",
            name="streamlit",
            login=True,
            password=streamlit_password,
            connection_limit=-1,
        )

        # Create Streamlit Database
        self.streamlit_database = Database(
            self,
            "streamlit-db",
            name="streamlit",
            owner=self.streamlit_role.name,
            connection_limit=-1,
            allow_connections=True,
        )