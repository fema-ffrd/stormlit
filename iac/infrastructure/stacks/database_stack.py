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
    A stack that creates and configures the PostgreSQL database infrastructure.

    This stack manages:
    1. Password generation for database users
    2. Secrets management in AWS Secrets Manager
    3. RDS PostgreSQL instance deployment
    4. Database user credentials and roles

    Database Users:
    - DB Admin: Root database administrator
    - PgSTAC Admin: Schema owner and migrations
    - PgSTAC Ingest: Write access for data ingestion
    - PgSTAC Read: Read-only access for queries

    Infrastructure Components:
    - Random Password Generator:
        * Secure password generation
        * Configurable length and complexity
        * Special character support

    - Secrets Manager:
        * Stores all database credentials
        * Username/password pairs as JSON
        * Managed access through IAM

    - RDS Instance:
        * PostgreSQL 17.2 engine
        * Custom parameter group
        * Automated backups
        * Encryption at rest

    Attributes:
        random_passwords (RandomPasswordConstruct): Password generation resource
        secrets (SecretsManagerConstruct): AWS Secrets Manager resources
        rds (RdsConstruct): RDS instance and configuration

    Parameters:
        scope (Construct): The scope in which this stack is defined
        id (str): The scoped construct ID
        config (EnvironmentConfig): Environment configuration settings
        subnet_ids (List[str]): List of subnet IDs for RDS placement
        rds_security_group_id (str): Security group ID for RDS instance

    Example:
        ```python
        db_stack = DatabaseStack(
            app,
            "myapp-prod-database",
            config,
            subnet_ids=["subnet-1", "subnet-2"],
            rds_security_group_id="sg-123"
        )
        ```

    Outputs:
        - RDS endpoint
        - DB admin secret ARN
        - PgSTAC admin secret ARN
        - PgSTAC ingest secret ARN
        - PgSTAC read secret ARN

    Notes:
        - Passwords are 20 characters with special characters
        - RDS configuration from DatabaseConfig
        - Dependencies managed to ensure proper creation order
        - Secret ARNs available for other stacks
        - All resources tagged for management
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
