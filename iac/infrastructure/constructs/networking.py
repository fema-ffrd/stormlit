from typing import List
from constructs import Construct
from cdktf_cdktf_provider_aws.vpc import Vpc
from cdktf_cdktf_provider_aws.subnet import Subnet
from cdktf_cdktf_provider_aws.internet_gateway import InternetGateway
from cdktf_cdktf_provider_aws.eip import Eip
from cdktf_cdktf_provider_aws.nat_gateway import NatGateway
from cdktf_cdktf_provider_aws.route_table import RouteTable
from cdktf_cdktf_provider_aws.route_table_association import RouteTableAssociation
from cdktf_cdktf_provider_aws.security_group import SecurityGroup
from cdktf_cdktf_provider_aws.security_group_rule import SecurityGroupRule
from cdktf_cdktf_provider_aws.route import Route
from config import EcsServiceConfig


class NetworkingConstruct(Construct):
    """
    A construct to create a complete AWS networking infrastructure.
    Includes security group updates for NLB access to ECS.
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        project_prefix: str,
        vpc_cidr: str,
        vpc_subnet_azs: List[str],
        environment: str,
        stac_api_config: EcsServiceConfig,
        tags: dict,
    ) -> None:
        super().__init__(scope, id)

        resource_prefix = f"{project_prefix}-{environment}"

        # Create VPC
        self.vpc = Vpc(
            self,
            "vpc",
            cidr_block=vpc_cidr,
            enable_dns_hostnames=True,
            enable_dns_support=True,
            tags={**tags, "Name": f"{resource_prefix}-vpc"},
        )

        # Create Internet Gateway
        igw = InternetGateway(
            self,
            "igw",
            vpc_id=self.vpc.id,
            tags={**tags, "Name": f"{resource_prefix}-igw"},
        )

        # Create public route table
        public_route_table = RouteTable(
            self,
            "public-rt",
            vpc_id=self.vpc.id,
            tags={**tags, "Name": f"{resource_prefix}-public-rt"},
        )
        Route(
            self,
            "public-route",
            route_table_id=public_route_table.id,
            destination_cidr_block="0.0.0.0/0",
            gateway_id=igw.id,
        )

        # Create private route table
        private_route_table = RouteTable(
            self,
            "private-rt",
            vpc_id=self.vpc.id,
            tags={**tags, "Name": f"{resource_prefix}-private-rt"},
        )

        self.public_subnets: List[Subnet] = []
        self.private_subnets: List[Subnet] = []

        eip_for_nat = Eip(
            self,
            "nat-eip",
            vpc=True,
            tags={**tags, "Name": f"{resource_prefix}-nat-eip"},
        )

        nat_gateway = None

        for i, az in enumerate(vpc_subnet_azs):
            public_subnet_cidr = f"10.0.{i * 2}.0/24"
            private_subnet_cidr = f"10.0.{(i * 2) + 1}.0/24"

            public_subnet = Subnet(
                self,
                f"public-subnet-{i + 1}",
                vpc_id=self.vpc.id,
                cidr_block=public_subnet_cidr,
                availability_zone=az,
                map_public_ip_on_launch=True,
                tags={
                    **tags,
                    "Name": f"{resource_prefix}-public-subnet-{i + 1}",
                    "Type": "Public",
                },
            )
            self.public_subnets.append(public_subnet)
            RouteTableAssociation(
                self,
                f"public-rta-{i + 1}",
                subnet_id=public_subnet.id,
                route_table_id=public_route_table.id,
            )

            private_subnet = Subnet(
                self,
                f"private-subnet-{i + 1}",
                vpc_id=self.vpc.id,
                cidr_block=private_subnet_cidr,
                availability_zone=az,
                tags={
                    **tags,
                    "Name": f"{resource_prefix}-private-subnet-{i + 1}",
                    "Type": "Private",
                },
            )
            self.private_subnets.append(private_subnet)
            RouteTableAssociation(
                self,
                f"private-rta-{i + 1}",
                subnet_id=private_subnet.id,
                route_table_id=private_route_table.id,
            )

            if i == 0:
                nat_gateway = NatGateway(
                    self,
                    "nat",
                    allocation_id=eip_for_nat.id,
                    subnet_id=public_subnet.id,
                    tags={**tags, "Name": f"{resource_prefix}-nat"},
                )

        if nat_gateway:
            Route(
                self,
                "private-route-to-nat",
                route_table_id=private_route_table.id,
                destination_cidr_block="0.0.0.0/0",
                nat_gateway_id=nat_gateway.id,
            )

        # ALB Security Group
        self.alb_security_group = SecurityGroup(
            self,
            "alb-sg",
            name=f"{resource_prefix}-alb-sg",
            vpc_id=self.vpc.id,
            description=f"Security group for {resource_prefix} Application Load Balancer",
            tags={**tags, "Name": f"{resource_prefix}-alb-sg"},
        )
        for port, desc_suffix in [(80, "HTTP"), (443, "HTTPS")]:
            SecurityGroupRule(
                self,
                f"alb-ingress-{port}",
                type="ingress",
                security_group_id=self.alb_security_group.id,
                from_port=port,
                to_port=port,
                protocol="tcp",
                cidr_blocks=["0.0.0.0/0"],
                description=f"Allow {desc_suffix} from Internet",
            )
        SecurityGroupRule(
            self,
            "alb-egress",
            type="egress",
            security_group_id=self.alb_security_group.id,
            from_port=0,
            to_port=0,
            protocol="-1",
            cidr_blocks=["0.0.0.0/0"],
            description="Allow all outbound traffic",
        )

        # ECS Tasks Security Group
        self.ecs_security_group = SecurityGroup(
            self,
            "ecs-sg",
            name=f"{resource_prefix}-ecs-sg",
            vpc_id=self.vpc.id,
            description=f"Security group for {resource_prefix} ECS tasks",
            tags={**tags, "Name": f"{resource_prefix}-ecs-sg"},
        )
        # ECS ingress from ALB for Stormlit (port 8501)
        SecurityGroupRule(
            self,
            "ecs-ingress-stormlit-from-alb",
            type="ingress",
            security_group_id=self.ecs_security_group.id,
            from_port=8501,
            to_port=8501,
            protocol="tcp",
            source_security_group_id=self.alb_security_group.id,
            description="Allow Stormlit traffic from ALB",
        )
        # ECS ingress from VPC CIDR for STAC API (NLB traffic)
        SecurityGroupRule(
            self,
            "ecs-ingress-stac-from-vpc-nlb",
            type="ingress",
            security_group_id=self.ecs_security_group.id,
            from_port=stac_api_config.container_port,
            to_port=stac_api_config.container_port,
            protocol="tcp",
            cidr_blocks=[vpc_cidr],
            description=f"Allow STAC API traffic from VPC (NLB) on port {stac_api_config.container_port}",
        )
        SecurityGroupRule(
            self,
            "ecs-self-ingress",
            type="ingress",
            security_group_id=self.ecs_security_group.id,
            from_port=0,
            to_port=0,
            protocol="-1",
            self_attribute=True,
            description="Allow ECS instances to communicate with each other",
        )
        SecurityGroupRule(
            self,
            "ecs-egress",
            type="egress",
            security_group_id=self.ecs_security_group.id,
            from_port=0,
            to_port=0,
            protocol="-1",
            cidr_blocks=["0.0.0.0/0"],
            description="Allow all outbound traffic",
        )

        # RDS Security Group
        self.rds_security_group = SecurityGroup(
            self,
            "rds-sg",
            name=f"{resource_prefix}-rds-sg",
            vpc_id=self.vpc.id,
            description=f"Security group for {resource_prefix} RDS instances",
            tags={**tags, "Name": f"{resource_prefix}-rds-sg"},
        )
        SecurityGroupRule(
            self,
            "rds-vpc-ingress",
            type="ingress",
            security_group_id=self.rds_security_group.id,
            from_port=5432,
            to_port=5432,
            protocol="tcp",
            source_security_group_id=self.ecs_security_group.id,
            description="Allow PostgreSQL access from ECS tasks",
        )
        SecurityGroupRule(
            self,
            "rds-vpc-ingress",
            type="ingress",
            security_group_id=self.rds_security_group.id,
            from_port=5432,
            to_port=5432,
            protocol="tcp",
            source_security_group_id="sg-0913eaec57c161f18",  # Stormlit Bastion SG
            description="Allow PostgreSQL access from Stormlit Bastion",
        )
        SecurityGroupRule(
            self,
            "rds-egress",
            type="egress",
            security_group_id=self.rds_security_group.id,
            from_port=0,
            to_port=0,
            protocol="-1",
            cidr_blocks=["0.0.0.0/0"],
            description="Allow all outbound traffic",
        )
