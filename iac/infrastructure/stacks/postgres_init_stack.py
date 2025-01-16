from constructs import Construct
from cdktf_cdktf_provider_postgresql.provider import PostgresqlProvider
from cdktf_cdktf_provider_postgresql.database import Database
from cdktf_cdktf_provider_postgresql.role import Role
from .base_stack import BaseStack
from config import EnvironmentConfig


class PostgresInitStack(BaseStack):
    def __init__(
        self,
        scope: Construct,
        id: str,
        config: EnvironmentConfig,
        *,
        host: str,
        port: int,
        db_admin_password: str,
        keycloak_password: str,
        pgstac_password: str,
    ) -> None:
        super().__init__(scope, id, config)

        # Provider config
        PostgresqlProvider(
            self,
            "postgresql",
            host=host,
            port=port,
            username=f"{config.project_prefix}_admin",
            password=db_admin_password,
            sslmode="require",
            superuser=False,  # so it will not try to read the password from Postgres
        )

        # Create keycloak role
        self.keycloak_role = Role(
            self,
            "keycloak-role",
            name=f"{config.project_prefix}_keycloak",
            login=True,
            password=keycloak_password,
            inherit=False,
        )

        # Create pgstac role
        self.pgstac_role = Role(
            self,
            "pgstac-role",
            name=f"{config.project_prefix}_pgstac",
            login=True,
            password=pgstac_password,
            inherit=False,
        )

        # Create keycloak database
        self.keycloak_database = Database(
            self,
            "keycloak-db",
            name="keycloak",
            owner=self.keycloak_role.name,
        )

        # Create pgstac database
        self.pgstac_database = Database(
            self,
            "pgstac-db",
            name="pgstac",
            owner=self.pgstac_role.name,
        )
