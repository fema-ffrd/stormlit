from dataclasses import dataclass
from typing import Dict, List
from cdktf import App, TerraformVariable


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
        publicly_accessible (bool): Indicates whether the RDS instance should be publicly accessible

    """

    instance_class: str
    allocated_storage: int
    max_allocated_storage: int
    deletion_protection: bool
    multi_az: bool
    backup_retention_period: int
    publicly_accessible: bool
    skip_final_snapshot: bool
    apply_immediately: bool
    monitoring_interval: int
    performance_insights_enabled: bool



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
class EcsServiceConfig:
    image_repository: str
    image_tag: str
    container_count: int
    cpu: int
    memory: int
    container_port: int


@dataclass
class EcsConfig:
    """
    Configuration class for ECS cluster settings.

    Attributes:
        instance_type (str): The type of EC2 instances used by ECS.
        instance_count (int): The number of ECS instances.
        stormlit_config (EcsServiceConfig): Configuration for the Stormlit service.
        stac_api_config (EcsServiceConfig): Configuration for the STAC FastAPI PGSTAC service.

    """

    instance_type: str
    instance_count: int
    stormlit_config: EcsServiceConfig
    stac_api_config: EcsServiceConfig


@dataclass
class ApplicationConfig:
    """
    Configuration class for application-specific settings.

    Attributes:
        domain_name (str): The domain name of the application.
        subdomain (str): The subdomain of the application.

    """

    domain_name: str
    subdomain: str


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
        environment (str): The environment type (e.g., dev, prod).
        region (str): The AWS region where resources will be deployed.
        vpc_cidr (str): The CIDR block for the VPC.
        vpc_subnet_azs (List[str]): The availability zones for the VPC subnets.
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
    vpc_subnet_azs: List[str]
    backend: BackendConfig
    database: DatabaseConfig
    application: ApplicationConfig
    ecs: EcsConfig
    secrets: SecretsConfig
    tags: Dict[str, str]


def get_development_config(app: App) -> EnvironmentConfig:
    """
    Retrieves the configuration settings for the development environment.

    Returns:
        EnvironmentConfig: A pre-defined configuration for the development environment.

    """
    return EnvironmentConfig(
        project_prefix="stormlit",
        environment="dev",
        region="us-east-1",
        vpc_cidr="10.0.0.0/16",
        vpc_subnet_azs=["us-east-1a", "us-east-1b"],
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
            backup_retention_period=7,
            publicly_accessible=False,
            skip_final_snapshot=True,
            apply_immediately=True,
            monitoring_interval=0,
            performance_insights_enabled=False,
        ),
        application=ApplicationConfig(
            domain_name="arc-apps.net",
            subdomain="stormlit-dev",
        ),
        ecs=EcsConfig(
            instance_type="t4g.medium",
            instance_count=1,
            stormlit_config=EcsServiceConfig(
                image_repository="ghcr.io/fema-ffrd/stormlit",
                image_tag=TerraformVariable(
                    app,
                    "stormlit_tag",
                    type="string",
                    description="Version tag for the stormlit image",
                    default="latest",  # fallback to 'latest' if not provided
                ),
                container_count=1,
                cpu=1024,
                memory=2560,
                container_port=8501,
            ),
            stac_api_config=EcsServiceConfig(
                image_repository="ghcr.io/stac-utils/stac-fastapi-pgstac",
                image_tag="4.0.0",
                container_count=1,
                cpu=512,
                memory=1024,
                container_port=8080,
            )
        ),
        secrets=SecretsConfig(
            database_admin_username="stormlit_admin",
            passwords=PasswordConfig(
                length=16,
                use_special=True,
            ),
        ),
        tags={
            "Environment": "dev",
            "Project": "stormlit",
            "ManagedBy": "cdktf",
        },
    )


def get_production_config(app: App) -> EnvironmentConfig:
    """
    Retrieves the configuration settings for the production environment.

    Returns:
        EnvironmentConfig: A pre-defined configuration for the production environment.

    """
    return EnvironmentConfig(
        project_prefix="stormlit",
        environment="prod",
        region="us-east-1",
        vpc_cidr="10.0.0.0/16",
        vpc_subnet_azs=["us-east-1a", "us-east-1b", "us-east-1c"],
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
            backup_retention_period=7,
            publicly_accessible=False,
            skip_final_snapshot=False,
            apply_immediately=False,
            monitoring_interval=60,
            performance_insights_enabled=True,
        ),
        application=ApplicationConfig(
            domain_name="arc-apps.net",
            subdomain="stormlit",
        ),
        ecs=EcsConfig(
            instance_type="t4g.medium",
            instance_count=1,
            stormlit_config=EcsServiceConfig(
                image_repository="ghcr.io/fema-ffrd/stormlit",
                image_tag=TerraformVariable(
                    app,
                    "stormlit_tag",
                    type="string",
                    description="Version tag for the stormlit image",
                    default="latest",  # fallback to 'latest' if not provided
                ),
                container_count=1,
                cpu=1024,
                memory=2560,
                container_port=8501,
            ),
            stac_api_config=EcsServiceConfig(
                image_repository="ghcr.io/stac-utils/stac-fastapi-pgstac",
                image_tag="4.0.0",
                container_count=1,
                cpu=512,
                memory=1024,
                container_port=8080,
            )
        ),
        secrets=SecretsConfig(
            database_admin_username="stormlit_admin",
            passwords=PasswordConfig(
                length=16,
                use_special=True,
            ),
        ),
        tags={
            "Environment": "prod",
            "Project": "stormlit",
            "ManagedBy": "cdktf",
        },
    )


def get_config(environment: str, app: App) -> EnvironmentConfig:
    """
    Retrieves the appropriate environment configuration based on the given environment type.

    Args:
        environment (str): The environment type (dev or prod).
        app (App): The CDKTF App instance.

    Returns:
        EnvironmentConfig: The corresponding configuration object for the specified environment.

    Raises:
        ValueError: If the specified environment type is not recognized.

    """
    configs = {
        "dev": get_development_config,
        "prod": get_production_config,
    }

    if environment not in configs:
        raise ValueError(f"Environment {environment} not found in configs")

    return configs[environment](app)
