from typing import List
from constructs import Construct
from cdktf import TerraformOutput
from config import EnvironmentConfig
from ..constructs.rds import RdsConstruct
from ..constructs.random_password import RandomPasswordConstruct
from ..constructs.secrets_manager import SecretsManagerConstruct
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
        private_subnets (List[str]): A list of private subnet IDs for the RDS instance.
        public_subnets (List[str]): A list of public subnet IDs for the RDS instance.
        rds_security_group (str): The security group ID for the RDS instance.

    Methods:
        __init__(self, scope, id, config): Initializes the database stack, setting up networking and RDS resources.

    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        config: EnvironmentConfig,
        private_subnets: List[str],
        public_subnets: List[str],
        rds_security_group: str,
    ) -> None:
        super().__init__(scope, id, config)

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
            keycloak_db_credentials={
                "username": f"{config.project_prefix}_keycloak",
                "password": self.random_passwords.keycloak_db_password.result,
            },
            pgstac_db_credentials={
                "username": f"{config.project_prefix}_pgstac",
                "password": self.random_passwords.pgstac_db_password.result,
            },
            tags=config.tags,
        )

        # Create RDS instance
        self.rds = RdsConstruct(
            self,
            "rds",
            project_prefix=config.project_prefix,
            environment=config.environment,
            private_subnets=private_subnets,
            public_subnets=public_subnets,
            security_group_id=rds_security_group,
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

        self.secrets.node.add_dependency(self.random_passwords)
        self.rds.node.add_dependency(self.secrets)

        # Create outputs
        TerraformOutput(
            self,
            "rds-endpoint",
            value=self.rds.db_instance.endpoint,
            description="RDS Instance Endpoint",
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
