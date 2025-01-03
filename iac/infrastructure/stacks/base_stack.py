from constructs import Construct
from cdktf import TerraformStack, S3Backend
from config import EnvironmentConfig
from cdktf_cdktf_provider_aws.provider import AwsProvider
from cdktf_cdktf_provider_aws.data_aws_region import DataAwsRegion


class BaseStack(TerraformStack):
    """
    A base stack that sets up common infrastructure for Terraform deployments.

    This stack provides the foundational setup required for deploying Terraform-managed infrastructure,
    including AWS provider configuration, region selection, and S3 backend setup for storing Terraform state.
    It ensures consistency and reusability across multiple stacks by managing shared AWS provider configurations
    and backend configurations.

    Attributes:
        current_region (DataAwsRegion): The current AWS region data.

    Parameters:
        scope (Construct): The scope in which this stack is defined.
        id (str): A unique identifier for the stack.
        config (EnvironmentConfig): The environment configuration object containing project settings.

    Methods:
        __init__(self, scope, id, config): Initializes the base stack, setting up AWS provider and backend
            configurations.

    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        config: EnvironmentConfig,
    ) -> None:
        super().__init__(scope, id)

        # Add AWS Provider
        AwsProvider(self, "aws", region=config.region)

        # Get current region
        self.current_region = DataAwsRegion(self, "current")

        # Configure S3 backend for storing Terraform state
        S3Backend(
            self,
            bucket=config.backend.s3_bucket,
            key=f"{config.project_prefix}-{config.environment}/stacks/{id}/terraform.tfstate",
            region=config.region,
            encrypt=True,
            dynamodb_table=config.backend.dynamodb_table,
        )
