#!/usr/bin/env python
from dataclasses import dataclass
from constructs import Construct
from cdktf import App, TerraformStack, S3Backend

BACKEND_DYNAMODB_TABLE_NAME = "mbi-dev-cdktf-backend-table"
BACKEND_S3_BUCKET_NAME = "mbi-dev-cdktf-backend-state"


@dataclass
class StormlitStackConfig:
    """Configurations for the StormlitStack"""

    environment: str
    region: str
    state_dynamodb_table_name: str
    state_s3_bucket_name: str
    state_key: str


class StormlitStack(TerraformStack):
    """
    StormlitStack is a CDKTF stack that defines the infrastructure for the Stormlit application.
    """

    def __init__(self, scope: Construct, config: StormlitStackConfig):
        super().__init__(scope, config.environment)

        S3Backend(
            self,
            bucket=config.state_s3_bucket_name,
            key=config.state_key,
            region=config.region,
            encrypt=True,
            dynamodb_table=config.state_dynamodb_table_name,
        )


test_config = StormlitStackConfig(
    environment="test",
    region="us-east-1",
    state_dynamodb_table_name=BACKEND_DYNAMODB_TABLE_NAME,
    state_s3_bucket_name=BACKEND_S3_BUCKET_NAME,
    state_key="stormlit-test/terraform.tfstate",
)

stormlit_test = App()
StormlitStack(stormlit_test, test_config)

stormlit_test.synth()
