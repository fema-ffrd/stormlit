from dataclasses import dataclass
from typing import Dict, List


@dataclass
class DatabaseConfig:
    """
    Configuration class for RDS database instance settings.

    Attributes:
        instance_class (str): The class/type of the RDS instance (e.g., db.t3.micro, db.t3.medium).
        allocated_storage (int): The amount of storage allocated to the RDS instance (in GiB).
        max_allocated_storage (int): The maximum amount of storage that can be allocated.
        deletion_protection (bool): Indicates whether deletion protection is enabled.
        multi_az (bool): Indicates if the RDS instance should be deployed in multiple Availability Zones for
            high availability.
        backup_retention_period (int): The number of days to retain backups.

    """

    instance_class: str
    allocated_storage: int
    max_allocated_storage: int
    deletion_protection: bool
    multi_az: bool
    backup_retention_period: int


@dataclass
class BackendConfig:
    """
    Configuration class for backend Terraform state storage.

    Attributes:
        s3_bucket (str): The name of the S3 bucket where Terraform state will be stored.
        dynamodb_table (str): The name of the DynamoDB table for locking the state.

    """

    s3_bucket: str
    dynamodb_table: str


@dataclass
class EcsConfig:
    """
    Configuration class for ECS cluster settings.

    Attributes:
        instance_type (str): The type of EC2 instances used by ECS.
        instance_count (int): The number of ECS instances.
        streamlit_container_count (int): The number of Streamlit containers to run.

    """

    instance_type: str
    instance_count: int
    streamlit_container_count: int


@dataclass
class ApplicationConfig:
    """
    Configuration class for application-specific settings.

    Attributes:
        domain_name (str): The domain name of the application.
        keycloak_admin_user (str): The admin user for Keycloak.
        keycloak_admin_password (str): The admin password for Keycloak (consider using AWS Secrets
            Manager for production).
        keycloak_image (str): The Docker image of Keycloak.
        streamlit_image (str): The Docker image for Streamlit.

    """

    domain_name: str
    keycloak_image: str
    streamlit_image: str


@dataclass
class PasswordConfig:
    """
    Configuration class for password generation settings.

    Attributes:
        length (int): The length of generated passwords.
        use_special (bool): Whether to include special characters in passwords.
        special_chars (str): The set of special characters to use in passwords.
    """

    length: int = 20
    use_special: bool = True
    special_chars: str = "!#$%&*()-_=+[]{}<>:?"


@dataclass
class SecretsConfig:
    """
    Configuration class for AWS Secrets Manager settings.

    Attributes:
        database_admin_username (str): The admin username for the database.
        passwords (PasswordConfig): Configuration for password generation.
    """

    database_admin_username: str
    passwords: PasswordConfig


@dataclass
class EnvironmentConfig:
    """
    Configuration class for environment-specific settings.

    Attributes:
        project_prefix (str): A prefix for naming resources to help differentiate between environments.
        environment (str): The environment type (e.g., development, production).
        region (str): The AWS region where resources will be deployed.
        vpc_cidr (str): The CIDR block for the VPC.
        backend (BackendConfig): The configuration for backend storage (S3 bucket, DynamoDB table).
        database (DatabaseConfig): The configuration for RDS database settings.
        application (ApplicationConfig): The configuration for application-specific settings.
        ecs (EcsConfig): The configuration for ECS instance settings.
        secrets (SecretsConfig): The configuration for AWS Secrets Manager settings.
        tags (Dict[str, str]): A dictionary of tags to apply to all resources.

    """

    project_prefix: str
    environment: str
    region: str
    vpc_cidr: str
    backend: BackendConfig
    database: DatabaseConfig
    application: ApplicationConfig
    ecs: EcsConfig
    secrets: SecretsConfig
    tags: Dict[str, str]


def get_development_config() -> EnvironmentConfig:
    """
    Retrieves the configuration settings for the development environment.

    Returns:
        EnvironmentConfig: A pre-defined configuration for the development environment.

    """
    return EnvironmentConfig(
        project_prefix="stormlit",
        environment="development",
        region="us-east-2",
        vpc_cidr="10.0.0.0/16",
        backend=BackendConfig(
            s3_bucket="cdktf-state-fema-ffrd",
            dynamodb_table="cdktf-state-lock-fema-ffrd",
        ),
        database=DatabaseConfig(
            instance_class="db.t4g.medium",
            allocated_storage=20,
            max_allocated_storage=100,
            deletion_protection=False,
            multi_az=False,
            backup_retention_period=7
        ),
        application=ApplicationConfig(
            domain_name="dev.example.com", # TODO Change domain name
            keycloak_image="quay.io/keycloak/keycloak:26.0.6",
            streamlit_image="latest",
        ),
        ecs=EcsConfig(
            instance_type="t4g.medium",
            instance_count=1,
            streamlit_container_count=1,
        ),
        secrets=SecretsConfig(
            database_admin_username="stormlit_admin",
            passwords=PasswordConfig(
                length=16,
                use_special=True,
            ),
        ),
        tags={
            "Environment": "development",
            "Project": "stormlit",
            "ManagedBy": "cdktf",
        },
    )


def get_production_config() -> EnvironmentConfig:
    """
    Retrieves the configuration settings for the production environment.

    Returns:
        EnvironmentConfig: A pre-defined configuration for the production environment.

    """
    return EnvironmentConfig(
        project_prefix="stormlit",
        environment="production",
        region="us-gov-east-1",
        vpc_cidr="10.1.0.0/16",
        backend=BackendConfig(
            s3_bucket="",  # TODO: Change bucket name
            dynamodb_table="",  # TODO: Change table name
        ),
        database=DatabaseConfig(
            instance_class="db.t3.medium",
            allocated_storage=50,
            max_allocated_storage=200,
            deletion_protection=True,
            multi_az=True,
            backup_retention_period=30,
        ),
        application=ApplicationConfig(
            domain_name="prod.example.com",  # TODO Change domain name
            keycloak_image="quay.io/keycloak/keycloak:26.0.6",
            streamlit_image="latest",
        ),
        ecs=EcsConfig(
            instance_type="t3.large",
            instance_count=2,
            streamlit_container_count=2,
        ),
        secrets=SecretsConfig(
            database_admin_username="stormlit_admin",
            passwords=PasswordConfig(
                length=32,
                use_special=True,
            ),
        ),
        tags={
            "Environment": "production",
            "Project": "stormlit",
            "ManagedBy": "cdktf",
        },
    )


def get_config(environment: str) -> EnvironmentConfig:
    """
    Retrieves the appropriate environment configuration based on the given environment type.

    Args:
        environment (str): The environment type (development or production).

    Returns:
        EnvironmentConfig: The corresponding configuration object for the specified environment.

    Raises:
        ValueError: If the specified environment type is not recognized.

    """
    configs = {
        "development": get_development_config,
        "production": get_production_config,
    }

    if environment not in configs:
        raise ValueError(f"Environment {environment} not found in configs")

    return configs[environment]()
