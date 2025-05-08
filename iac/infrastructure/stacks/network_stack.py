from constructs import Construct
from cdktf import TerraformOutput
from config import EnvironmentConfig
from ..constructs.networking import NetworkingConstruct
from .base_stack import BaseStack


class NetworkStack(BaseStack):
    """
    A stack that creates the foundational AWS networking infrastructure.
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        config: EnvironmentConfig,
    ) -> None:
        super().__init__(scope, id, config)

        self.networking = NetworkingConstruct(
            self, "networking",
            project_prefix=config.project_prefix,
            vpc_cidr=config.vpc_cidr,
            vpc_subnet_azs=config.vpc_subnet_azs,
            environment=config.environment,
            stac_api_config=config.ecs.stac_api_config,
            tags=config.tags,
        )

        self.vpc_id_output = TerraformOutput(
            self, "vpc-id", value=self.networking.vpc.id, description="VPC ID",
        )
        self.public_subnet_ids_output = TerraformOutput(
            self, "public-subnet-ids",
            value=[subnet.id for subnet in self.networking.public_subnets],
            description="Public Subnet IDs",
        )
        self.private_subnet_ids_output = TerraformOutput(
            self, "private-subnet-ids",
            value=[subnet.id for subnet in self.networking.private_subnets],
            description="Private Subnet IDs",
        )
        self.alb_security_group_id_output = TerraformOutput(
            self, "alb_security_group_id",
            value=self.networking.alb_security_group.id,
            description="ALB Security Group ID",
        )
        self.ecs_security_group_id_output = TerraformOutput(
            self, "ecs_security_group_id",
            value=self.networking.ecs_security_group.id,
            description="ECS Security Group ID",
        )
        self.rds_security_group_id_output = TerraformOutput(
            self, "rds_security_group_id",
            value=self.networking.rds_security_group.id,
            description="RDS Security Group ID",
        )
