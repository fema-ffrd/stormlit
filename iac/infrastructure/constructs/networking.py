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


class NetworkingConstruct(Construct):
    """
    A Construct to create a complete networking setup for the AWS environment.

    This construct manages the creation of a VPC, subnets, internet gateways, NAT gateways, route
    tables, and associated security groups. It ensures network components are configured according
    to best practices for public and private subnets, enabling connectivity for ECS, RDS, and other
    AWS services. Security groups are set up to control inbound and outbound traffic.

    Attributes:
        vpc (Vpc): The VPC created by this construct.
        public_subnets (List[Subnet]): A list of public subnets created by this construct.
        private_subnets (List[Subnet]): A list of private subnets created by this construct.
        alb_security_group (SecurityGroup): The security group associated with the Application Load Balancer.
        ecs_security_group (SecurityGroup): The security group associated with ECS tasks.
        rds_security_group (SecurityGroup): The security group associated with RDS instances.

    Parameters:
        scope (Construct): The scope in which this construct is defined.
        id (str): A unique identifier for the construct.
        project_prefix (str): A prefix for naming resources to help differentiate between environments.
        vpc_cidr (str): The CIDR block for the VPC.
        environment (str): The environment name (e.g., `development`, `production`) for tagging purposes.
        tags (dict): A dictionary of tags to apply to all resources created by this construct.

    Methods:
        __init__(self, scope, id, ...): Initializes the networking setup for the AWS environment.

    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        project_prefix: str,
        vpc_cidr: str,
        environment: str,
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

        # Add route to the internet gateway
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

        # Create subnets across multiple AZs
        self.public_subnets: List[Subnet] = []
        self.private_subnets: List[Subnet] = []

        # Create NAT Gateway in the first public subnet
        eip = Eip(
            self,
            "nat-eip",
            vpc=True,
            tags={**tags, "Name": f"{resource_prefix}-nat-eip"},
        )

        # Create subnets in 3 availability zones
        azs = ["us-east-1a", "us-east-1b", "us-east-1c"]

        # For VPC CIDR 10.0.0.0/16, create subnets in 10.0.x.0/24 ranges
        for i, az in enumerate(azs):
            subnet_number = i * 2  # 0, 2, 4 for public subnets

            # Public subnet
            public_subnet = Subnet(
                self,
                f"public-subnet-{i+1}",
                vpc_id=self.vpc.id,
                cidr_block=f"10.0.{subnet_number}.0/24",
                availability_zone=az,
                map_public_ip_on_launch=True,
                tags={
                    **tags,
                    "Name": f"{resource_prefix}-public-subnet-{i+1}",
                    "Type": "Public",
                },
            )
            self.public_subnets.append(public_subnet)

            # Associate public subnet with public route table
            RouteTableAssociation(
                self,
                f"public-rta-{i+1}",
                subnet_id=public_subnet.id,
                route_table_id=public_route_table.id,
            )

            # Private subnet uses the next subnet number
            private_subnet = Subnet(
                self,
                f"private-subnet-{i+1}",
                vpc_id=self.vpc.id,
                cidr_block=f"10.0.{subnet_number + 1}.0/24",
                availability_zone=az,
                tags={
                    **tags,
                    "Name": f"{resource_prefix}-private-subnet-{i+1}",
                    "Type": "Private",
                },
            )
            self.private_subnets.append(private_subnet)

            RouteTableAssociation(
                self,
                f"private-rta-{i+1}",
                subnet_id=private_subnet.id,
                route_table_id=private_route_table.id,
            )

            # Create NAT Gateway in first public subnet only
            if i == 0:
                nat_gateway = NatGateway(
                    self,
                    "nat",
                    allocation_id=eip.id,
                    subnet_id=public_subnet.id,
                    tags={**tags, "Name": f"{resource_prefix}-nat"},
                )

                # Add route through NAT Gateway for private subnets
                Route(
                    self,
                    "private-route",
                    route_table_id=private_route_table.id,
                    destination_cidr_block="0.0.0.0/0",
                    nat_gateway_id=nat_gateway.id,
                )

        # Create security groups
        # ALB Security Group
        self.alb_security_group = SecurityGroup(
            self,
            "alb-sg",
            name=f"{resource_prefix}-alb-sg",
            vpc_id=self.vpc.id,
            description=f"Security group for {resource_prefix} Application Load Balancer",
            tags={**tags, "Name": f"{resource_prefix}-alb-sg"},
        )

        # ALB ingress rules for public access
        alb_ingress_rules = [
            ("http", 80, "HTTP"),
            ("https", 443, "HTTPS"),
            ("keycloak", 8080, "Keycloak"),
            ("streamlit", 8501, "Streamlit"),
        ]

        for rule_id, port, description in alb_ingress_rules:
            SecurityGroupRule(
                self,
                f"alb-ingress-{rule_id}",
                type="ingress",
                security_group_id=self.alb_security_group.id,
                from_port=port,
                to_port=port,
                protocol="tcp",
                cidr_blocks=["0.0.0.0/0"],
                description=description,
            )

        # ALB egress rule
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

        # ECS ingress rules - Allow traffic from ALB
        ecs_ingress_rules = [
            ("keycloak", 8080, "Keycloak from ALB"),
            ("streamlit", 8501, "Streamlit from ALB"),
            ("ecs-agent", 51678, "ECS Agent"),
            ("ecs-telemetry", 51679, "ECS Telemetry"),
        ]

        for rule_id, port, description in ecs_ingress_rules:
            SecurityGroupRule(
                self,
                f"ecs-ingress-{rule_id}",
                type="ingress",
                security_group_id=self.ecs_security_group.id,
                from_port=port,
                to_port=port,
                protocol="tcp",
                source_security_group_id=self.alb_security_group.id,
                description=description,
            )

        # Allow ECS instances to communicate with each other
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

        # ECS egress rule
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

        # RDS ingress rule - Allow access from ECS tasks
        SecurityGroupRule(
            self,
            "rds-ingress",
            type="ingress",
            security_group_id=self.rds_security_group.id,
            from_port=5432,
            to_port=5432,
            protocol="tcp",
            source_security_group_id=self.ecs_security_group.id,
            description="PostgreSQL access from ECS tasks",
        )

        # RDS egress rule
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
