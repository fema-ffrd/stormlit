from typing import Dict
import json
from constructs import Construct
from cdktf_cdktf_provider_aws.secretsmanager_secret import SecretsmanagerSecret
from cdktf_cdktf_provider_aws.secretsmanager_secret_version import (
    SecretsmanagerSecretVersion,
)


class SecretsManagerConstruct(Construct):
    """
    A Construct for managing sensitive credentials using AWS Secrets Manager.

    This construct facilitates the creation and management of secrets in AWS Secrets Manager,
    providing a secure way to store and access sensitive information such as database credentials,
    API keys, and application secrets. It supports both single-value secrets and JSON-structured
    secrets with multiple key-value pairs.

    Attributes:
        database_secret (SecretsmanagerSecret): The secret containing database credentials.
        keycloak_secret (SecretsmanagerSecret): The secret containing Keycloak admin credentials.

    Parameters:
        scope (Construct): The scope in which this construct is defined.
        id (str): The unique identifier of the construct.
        project_prefix (str): A prefix for project-related resource names to ensure uniqueness.
        environment (str): The environment name (e.g., `development`, `production`) for resource differentiation.
        database_credentials (Dict[str, str]): Dictionary containing database credentials (username, password).
        keycloak_credentials (Dict[str, str]): Dictionary containing Keycloak admin credentials.
        tags (dict): A dictionary of tags to apply to all resources created by this construct.

    Methods:
        __init__(self, scope, id, ...): Initializes the Secrets Manager construct, creating necessary secrets
            and their versions.
        _create_secret_with_version(self, secret_id: str, name: str, secret_value: Dict[str, str]): Helper method
            to create a secret and its initial version.
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        project_prefix: str,
        environment: str,
        database_credentials: Dict[str, str],
        keycloak_credentials: Dict[str, str],
        keycloak_db_credentials: Dict[str, str],
        pgstac_db_credentials: Dict[str, str],
        tags: dict,
    ) -> None:
        super().__init__(scope, id)

        resource_prefix = f"{project_prefix}-{environment}"

        # Create database admin credentials secret
        self.database_secret = self._create_secret_with_version(
            "database-secret",
            f"{resource_prefix}-db-creds",
            database_credentials,
            tags,
        )

        # Create Keycloak admin credentials secret
        self.keycloak_secret = self._create_secret_with_version(
            "keycloak-secret",
            f"{resource_prefix}-kc-creds",
            keycloak_credentials,
            tags,
        )

        # Create Keycloak database user credentials secret
        self.keycloak_db_secret = self._create_secret_with_version(
            "keycloak-db-secret",
            f"{resource_prefix}-kc-db-creds",
            keycloak_db_credentials,
            tags,
        )

        # Create PGSTAC database user credentials secret
        self.pgstac_db_secret = self._create_secret_with_version(
            "pgstac-db-secret",
            f"{resource_prefix}-pgstac-db-creds",
            pgstac_db_credentials,
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
