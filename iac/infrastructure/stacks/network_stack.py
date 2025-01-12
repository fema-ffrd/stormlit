from constructs import Construct
from cdktf import TerraformOutput
from config import EnvironmentConfig
from ..constructs.networking import NetworkingConstruct
from ..constructs.ecr import EcrConstruct
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
            environment=config.environment,
            tags=config.tags,
        )

        # Create ECR repositories
        self.ecr = EcrConstruct(
            self,
            "ecr",
            project_prefix=config.project_prefix,
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

        TerraformOutput(
            self,
            "streamlit-repo-url",
            value=self.ecr.streamlit_repository.repository_url,
            description="Streamlit ECR Repository URL",
        )
