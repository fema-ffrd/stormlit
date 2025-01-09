from constructs import Construct
from cdktf import TerraformOutput, Token
from config import EnvironmentConfig
from ..constructs.networking import NetworkingConstruct
from ..constructs.rds import RdsConstruct
from ..constructs.random_password import RandomPasswordConstruct
from ..constructs.secrets_manager import SecretsManagerConstruct
from ..constructs.postgres_init import PostgresInitConstruct
from .base_stack import BaseStack


class DatabaseStack(BaseStack):
    """
    A stack to deploy database infrastructure, including RDS and networking configurations.

    This stack sets up necessary components for a relational database system, including networking resources
    like VPC, subnets, and security groups, and provisions the RDS instance. It ensures proper network isolation,
    high availability, and security settings for the database infrastructure.

    Attributes:
        networking (NetworkingConstruct): The networking resources required for RDS deployment.
        rds (RdsConstruct): The RDS instance managed by this stack.

    Parameters:
        scope (Construct): The scope in which this stack is defined.
        id (str): A unique identifier for the stack.
        config (EnvironmentConfig): The environment configuration object containing project settings.

    Methods:
        __init__(self, scope, id, config): Initializes the database stack, setting up networking and RDS resources.

    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        config: EnvironmentConfig,
    ) -> None:
        super().__init__(scope, id, config)

        # Create networking resources
        self.networking = NetworkingConstruct(
            self,
            "networking",
            project_prefix=config.project_prefix,
            vpc_cidr=config.vpc_cidr,
            environment=config.environment,
            tags=config.tags,
        )

        self.random_passwords = RandomPasswordConstruct(
            self,
            "random-passwords",
            min_length=20,
            special=True,
        )

        # Create secrets manager resources with random passwords
        self.secrets = SecretsManagerConstruct(
            self,
            "secrets",
            project_prefix=config.project_prefix,
            environment=config.environment,
            database_credentials={
                "username": f"{config.project_prefix}_admin",
                "password": self.random_passwords.database_password.result,
            },
            keycloak_credentials={
                "admin_user": "admin",
                "admin_password": self.random_passwords.keycloak_password.result,
            },
            streamlit_credentials={
                "admin_user": "admin",
                "admin_password": self.random_passwords.streamlit_password.result,
            },
            tags=config.tags,
        )

        # Create RDS instance
        self.rds = RdsConstruct(
            self,
            "rds",
            project_prefix=config.project_prefix,
            environment=config.environment,
            private_subnets=self.networking.private_subnets,
            public_subnets=self.networking.public_subnets,
            security_group=self.networking.rds_security_group,
            instance_class=config.database.instance_class,
            allocated_storage=config.database.allocated_storage,
            max_allocated_storage=config.database.max_allocated_storage,
            multi_az=config.database.multi_az,
            deletion_protection=config.database.deletion_protection,
            backup_retention_period=config.database.backup_retention_period,
            master_username=f"{config.project_prefix}_admin",
            master_password=self.random_passwords.database_password.result,
            tags=config.tags,
        )

        # Initialize PostgreSQL databases after RDS is created
        self.postgres_init = PostgresInitConstruct(
            self,
            "postgres-init",
            host=Token.as_string(f"${{split(\":\", {self.rds.db_instance.endpoint})[0]}}"),
            port=5432,
            superuser=f"{config.project_prefix}_admin",
            superuser_password=self.random_passwords.database_password.result,
            keycloak_password=self.random_passwords.keycloak_password.result,
            streamlit_password=self.random_passwords.streamlit_password.result,
        )

        self.secrets.node.add_dependency(self.random_passwords)
        self.rds.node.add_dependency(self.networking)
        self.rds.node.add_dependency(self.secrets)
        self.postgres_init.node.add_dependency(self.rds)
        self.postgres_init.node.add_dependency(self.secrets)
        self.postgres_init.node.add_dependency(self.random_passwords)
        self.postgres_init.node.add_dependency(self.networking)

        # Create outputs
        TerraformOutput(
            self,
            "vpc-id",
            value=self.networking.vpc.id,
            description="VPC ID",
        )

        TerraformOutput(
            self,
            "public-subnet-ids",
            value=[subnet.id for subnet in self.networking.public_subnets],
            description="Public Subnet IDs",
        )

        TerraformOutput(
            self,
            "private-subnet-ids",
            value=[subnet.id for subnet in self.networking.private_subnets],
            description="Private Subnet IDs",
        )

        TerraformOutput(
            self,
            "rds-endpoint",
            value=self.rds.db_instance.endpoint,
            description="RDS Instance Endpoint",
        )

        TerraformOutput(
            self,
            "alb-security-group-id",
            value=self.networking.alb_security_group.id,
            description="Application Load Balancer Security Group ID",
        )

        TerraformOutput(
            self,
            "database-secret-arn",
            value=self.secrets.database_secret.arn,
            description="Database Credentials Secret ARN",
        )

        TerraformOutput(
            self,
            "keycloak-secret-arn",
            value=self.secrets.keycloak_secret.arn,
            description="Keycloak Credentials Secret ARN",
        )

        TerraformOutput(
            self,
            "streamlit-secret-arn",
            value=self.secrets.streamlit_secret.arn,
            description="Streamlit Credentials Secret ARN",
        )
