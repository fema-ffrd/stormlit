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
        subnet_ids: List[str],
        rds_security_group_id: str,
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
            db_admin_credentials={
                "username": f"{config.project_prefix}_admin",
                "password": self.random_passwords.db_admin_password.result,
            },
            pgstac_admin_credentials={
                "username": "pgstac_admin",
                "password": self.random_passwords.pgstac_admin_password.result,
            },
            pgstac_ingest_credentials={
                "username": "pgstac_ingest",
                "password": self.random_passwords.pgstac_ingest_password.result,
            },
            pgstac_read_credentials={
                "username": "pgstac_read",
                "password": self.random_passwords.pgstac_read_password.result,
            },
            tags=config.tags,
        )

        # Create RDS instance
        self.rds = RdsConstruct(
            self,
            "rds",
            project_prefix=config.project_prefix,
            environment=config.environment,
            subnet_ids=subnet_ids,
            security_group_id=rds_security_group_id,
            db_config=config.database,
            master_username=f"{config.project_prefix}_admin",
            master_password=self.random_passwords.db_admin_password.result,
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
            "db-admin-secret-arn",
            value=self.secrets.db_admin_secret.arn,
            description="Database Credentials Secret ARN",
        )

        TerraformOutput(
            self,
            "pgstac-admin-secret-arn",
            value=self.secrets.pgstac_admin_secret.arn,
            description="PgSTAC Admin Credentials Secret ARN",
        )

        TerraformOutput(
            self,
            "pgstac-ingest-secret-arn",
            value=self.secrets.pgstac_ingest_secret.arn,
            description="PgSTAC Ingest Credentials Secret ARN",
        )

        TerraformOutput(
            self,
            "pgstac-read-secret-arn",
            value=self.secrets.pgstac_read_secret.arn,
            description="PgSTAC Read Credentials Secret ARN",
        )
