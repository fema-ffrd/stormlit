from typing import Dict
import json
from constructs import Construct
from cdktf_cdktf_provider_aws.secretsmanager_secret import SecretsmanagerSecret
from cdktf_cdktf_provider_aws.secretsmanager_secret_version import (
    SecretsmanagerSecretVersion,
)


class SecretsManagerConstruct(Construct):
    """
    A construct that creates secrets in AWS Secrets Manager.

    This construct creates secrets in AWS Secrets Manager and stores the initial version of the secret.

    Attributes:
        db_admin_secret (SecretsmanagerSecret): The secret for database admin credentials.
        pgstac_admin_secret (SecretsmanagerSecret): The secret for PgSTAC admin credentials.
        pgstac_ingest_secret (SecretsmanagerSecret): The secret for PgSTAC ingest credentials.
        pgstac_read_secret (SecretsmanagerSecret): The secret for PgSTAC read-only credentials.

    Args:
        scope (Construct): The parent construct of this construct.
        id (str): The ID of this construct.
        project_prefix (str): A prefix for naming resources to help differentiate between environments.
        environment (str): The environment for which to create secrets.
        db_admin_credentials (Dict[str, str]): The database admin credentials to store in the secret.
        pgstac_admin_credentials (Dict[str, str]): The PgSTAC admin credentials to store in the secret.
        pgstac_ingest_credentials (Dict[str, str]): The PgSTAC ingest credentials to store in the secret.
        pgstac_read_credentials (Dict[str, str]): The PgSTAC read-only credentials to store in the secret.
        tags (dict): Tags to apply to the secret.

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
            f"{resource_prefix}-db-admin-creds",
            db_admin_credentials,
            tags,
        )

        # Create PgSTAC credentials secrets
        self.pgstac_admin_secret = self._create_secret_with_version(
            "pgstac-admin-secret",
            f"{resource_prefix}-pgstac-admin-creds",
            pgstac_admin_credentials,
            tags,
        )

        self.pgstac_ingest_secret = self._create_secret_with_version(
            "pgstac-ingest-secret",
            f"{resource_prefix}-pgstac-ingest-creds",
            pgstac_ingest_credentials,
            tags,
        )

        self.pgstac_read_secret = self._create_secret_with_version(
            "pgstac-read-secret",
            f"{resource_prefix}-pgstac-read-creds",
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
