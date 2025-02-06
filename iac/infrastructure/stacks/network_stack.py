from constructs import Construct
from cdktf import TerraformOutput
from config import EnvironmentConfig
from ..constructs.networking import NetworkingConstruct
from .base_stack import BaseStack


class NetworkStack(BaseStack):
    """
    Initializes the network stack, setting up networking and ECR resources.
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        config: EnvironmentConfig,
    ) -> None:
        super().__init__(scope, id, config)

        # Create networking resources
        self.networking = NetworkingConstruct(
            self,
            "networking",
            project_prefix=config.project_prefix,
            vpc_cidr=config.vpc_cidr,
            vpc_subnet_azs=config.vpc_subnet_azs,
            environment=config.environment,
            tags=config.tags,
        )

        TerraformOutput(
            self,
            "vpc-id",
            value=self.networking.vpc.id,
            description="VPC ID",
        )

        TerraformOutput(
            self,
            "public-subnet-ids",
            value=[subnet.id for subnet in self.networking.public_subnets],
            description="Public Subnet IDs",
        )

        TerraformOutput(
            self,
            "private-subnet-ids",
            value=[subnet.id for subnet in self.networking.private_subnets],
            description="Private Subnet IDs",
        )
