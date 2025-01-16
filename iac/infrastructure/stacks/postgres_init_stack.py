from constructs import Construct
from cdktf_cdktf_provider_postgresql.provider import PostgresqlProvider
from cdktf_cdktf_provider_postgresql.database import Database
from cdktf_cdktf_provider_postgresql.role import Role
from .base_stack import BaseStack
from config import EnvironmentConfig


class PostgresInitStack(BaseStack):
    """ """

    def __init__(
        self,
        scope: Construct,
        id: str,
        config: EnvironmentConfig,
        *,
        host: str,
        port: int,
        superuser_password: str,
        keycloak_password: str,
        pgstac_password: str,
    ) -> None:
        super().__init__(scope, id, config)

        # Configure PostgreSQL Provider
        PostgresqlProvider(
            self,
            "postgresql",
            host=host,
            port=port,
            username=f"{config.project_prefix}_admin",
            password=superuser_password,
            sslmode="require",
            connect_timeout=60,
            max_connections=5,
            superuser=False,
            expected_version="16.6",
        )

        # Create Keycloak Role
        self.keycloak_role = Role(
            self,
            "keycloak-role",
            name=f"{config.project_prefix}_keycloak",
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

        # Create PgStac Role
        self.pgstac_role = Role(
            self,
            "pgstac-role",
            name=f"{config.project_prefix}_pgstac",
            login=True,
            password=pgstac_password,
            connection_limit=-1,  # Unlimited connections
        )

        # Create PgStac Database
        self.pgstac_database = Database(
            self,
            "pgstac-db",
            name="pgstac",
            owner=self.pgstac_role.name,
            connection_limit=-1,
            allow_connections=True,
        )
