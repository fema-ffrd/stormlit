from constructs import Construct
from cdktf import TerraformOutput
from config import EnvironmentConfig
from ..constructs.networking import NetworkingConstruct
from .base_stack import BaseStack


class NetworkStack(BaseStack):
    """
    A stack that creates the foundational AWS networking infrastructure.

    This stack establishes the core networking components including:
    1. VPC with custom CIDR block
    2. Public and private subnets across multiple AZs
    3. Internet and NAT Gateways
    4. Route tables and security groups
    5. Network ACLs and routing

    Network Architecture:
    - VPC:
        * Custom CIDR block
        * DNS hostnames enabled
        * Multiple Availability Zones

    - Subnets:
        * Public subnets for internet-facing resources
        * Private subnets for internal resources
        * Multi-AZ deployment for high availability

    - Security:
        * Security groups for ALB, ECS, and RDS
        * Network ACLs for subnet-level security
        * Isolated private subnets

    Attributes:
        networking (NetworkingConstruct): The networking infrastructure resources

    Parameters:
        scope (Construct): The scope in which this stack is defined
        id (str): The scoped construct ID
        config (EnvironmentConfig): Environment configuration containing:
            - project_prefix: Resource naming prefix
            - vpc_cidr: VPC CIDR block
            - vpc_subnet_azs: List of AZs for subnet placement
            - environment: Environment name
            - tags: Resource tags

    Outputs:
        - VPC ID
        - Public subnet IDs
        - Private subnet IDs

    Example:
        ```python
        network = NetworkStack(
            app,
            "myapp-prod-network",
            config=EnvironmentConfig(
                project_prefix="myapp",
                vpc_cidr="10.0.0.0/16",
                vpc_subnet_azs=["us-east-1a", "us-east-1b"],
                environment="prod",
                tags={"Environment": "production"}
            )
        )
        ```

    Notes:
        - Creates basis for multi-tier architecture
        - Supports high availability deployments
        - Enables internal and external access patterns
        - All resources properly tagged
        - Outputs available for other stacks
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
