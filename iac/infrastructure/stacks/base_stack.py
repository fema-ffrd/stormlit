from constructs import Construct
from cdktf import TerraformStack, S3Backend
from config import EnvironmentConfig
from cdktf_cdktf_provider_aws.provider import AwsProvider
from cdktf_cdktf_provider_aws.data_aws_region import DataAwsRegion


class BaseStack(TerraformStack):
    """
    A foundational stack that provides common infrastructure configuration.

    This base stack establishes core infrastructure settings including:
    1. AWS provider configuration
    2. S3 backend for Terraform state
    3. DynamoDB table for state locking
    4. Region settings and data

    Purpose:
    - Provides consistent infrastructure configuration
    - Ensures proper state management
    - Enables stack composition
    - Standardizes provider setup

    Features:
    - S3 Backend:
        * Encrypted state storage
        * State locking via DynamoDB
        * Environment-specific state paths

    - AWS Provider:
        * Region configuration
        * Standard provider settings
        * Region data accessibility

    Attributes:
        current_region (DataAwsRegion): Information about the current AWS region

    Parameters:
        scope (Construct): The scope in which this stack is defined
        id (str): The scoped construct ID
        config (EnvironmentConfig): Environment configuration containing:
            - project_prefix: Resource naming prefix
            - environment: Environment name
            - region: AWS region
            - backend: S3 and DynamoDB configuration

    Example:
        ```python
        class MyStack(BaseStack):
            def __init__(self, scope: Construct, id: str, config: EnvironmentConfig):
                super().__init__(scope, id, config)
                # Add stack-specific resources
        ```

    Notes:
        - Used as base class for other stacks
        - Configures remote state management
        - Ensures consistent provider setup
        - Supports multi-environment deployments
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
