from typing import Dict
import json
from constructs import Construct
from cdktf_cdktf_provider_aws.secretsmanager_secret import SecretsmanagerSecret
from cdktf_cdktf_provider_aws.secretsmanager_secret_version import (
    SecretsmanagerSecretVersion,
)


class SecretsManagerConstruct(Construct):
    """
    A construct for managing database credentials in AWS Secrets Manager.

    This construct creates and manages secrets for database access credentials:
    1. Database admin credentials
    2. PgSTAC admin credentials
    3. PgSTAC ingest user credentials
    4. PgSTAC read-only user credentials

    Each secret:
    - Stores username and password as JSON
    - Has a unique name with environment prefix
    - Includes description and tags
    - Creates initial secret version
    - Format: {"username": "user", "password": "pass"}

    Secret Hierarchy:
    - Database Admin: Root database administrator
    - PgSTAC Admin: PgSTAC schema owner and migrations
    - PgSTAC Ingest: Write access for data ingestion
    - PgSTAC Read: Read-only access for queries

    Attributes:
        db_admin_secret (SecretsmanagerSecret): Database admin credentials secret
        pgstac_admin_secret (SecretsmanagerSecret): PgSTAC admin credentials secret
        pgstac_ingest_secret (SecretsmanagerSecret): PgSTAC ingest credentials secret
        pgstac_read_secret (SecretsmanagerSecret): PgSTAC read-only credentials secret

    Parameters:
        scope (Construct): The scope in which this construct is defined
        id (str): The scoped construct ID
        project_prefix (str): Prefix for resource names
        environment (str): Environment name (e.g., "prod", "dev")
        db_admin_credentials (Dict[str, str]): Database admin username and password
        pgstac_admin_credentials (Dict[str, str]): PgSTAC admin username and password
        pgstac_ingest_credentials (Dict[str, str]): PgSTAC ingest username and password
        pgstac_read_credentials (Dict[str, str]): PgSTAC read-only username and password
        tags (dict): Tags to apply to all secrets

    Example:
        ```python
        secrets = SecretsManagerConstruct(
            self,
            "secrets",
            project_prefix="myapp",
            environment="prod",
            db_admin_credentials={
                "username": "admin",
                "password": generated_password
            },
            pgstac_admin_credentials={
                "username": "pgstac_admin",
                "password": generated_password
            },
            pgstac_ingest_credentials={
                "username": "pgstac_ingest",
                "password": generated_password
            },
            pgstac_read_credentials={
                "username": "pgstac_read",
                "password": generated_password
            },
            tags={"Environment": "production"}
        )
        ```

    Notes:
        - Secrets are created with initial versions
        - Credentials stored in JSON format
        - Secret names include project and environment prefix
        - All secrets are tagged for management
        - Secrets can be referenced by ARN in other resources
        - Suitable for use with ECS task definitions
        - Integrated with AWS IAM for access control
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        project_prefix: str,
        environment: str,
        db_admin_credentials: Dict[str, str],
        pgstac_admin_credentials: Dict[str, str],
        pgstac_ingest_credentials: Dict[str, str],
        pgstac_read_credentials: Dict[str, str],
        tags: dict,
    ) -> None:
        super().__init__(scope, id)

        resource_prefix = f"{project_prefix}-{environment}"

        # Create database admin credentials secret
        self.db_admin_secret = self._create_secret_with_version(
            "db-admin-secret",
            f"{resource_prefix}-db-admin",
            db_admin_credentials,
            tags,
        )

        # Create PgSTAC credentials secrets
        self.pgstac_admin_secret = self._create_secret_with_version(
            "pgstac-admin-secret",
            f"{resource_prefix}-pgstac-admin",
            pgstac_admin_credentials,
            tags,
        )

        self.pgstac_ingest_secret = self._create_secret_with_version(
            "pgstac-ingest-secret",
            f"{resource_prefix}-pgstac-ingest",
            pgstac_ingest_credentials,
            tags,
        )

        self.pgstac_read_secret = self._create_secret_with_version(
            "pgstac-read-secret",
            f"{resource_prefix}-pgstac-read",
            pgstac_read_credentials,
            tags,
        )

    def _create_secret_with_version(
        self,
        secret_id: str,
        name: str,
        secret_value: Dict[str, str],
        tags: dict,
    ) -> SecretsmanagerSecret:
        """
        Helper method to create a secret and its initial version.

        Args:
            secret_id (str): The unique identifier for the secret within this construct.
            name (str): The name of the secret in AWS Secrets Manager.
            secret_value (Dict[str, str]): The secret value to store.
            tags (dict): Tags to apply to the secret.

        Returns:
            SecretsmanagerSecret: The created secret resource.
        """
        secret = SecretsmanagerSecret(
            self,
            secret_id,
            name=name,
            description=f"Managed by CDK for Terraform - {name}",
            tags=tags,
        )

        SecretsmanagerSecretVersion(
            self,
            f"{secret_id}-version",
            secret_id=secret.id,
            secret_string=json.dumps(secret_value),
        )

        return secret
