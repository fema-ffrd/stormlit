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
    A construct to create a complete AWS networking infrastructure.

    This construct creates and configures a full VPC networking stack with:
    1. VPC with custom CIDR block and DNS settings
    2. Public and private subnets across multiple AZs
    3. Internet Gateway for public subnets
    4. NAT Gateway for private subnet internet access
    5. Route tables and route associations
    6. Security groups for ALB, ECS, and RDS

    Network Architecture:
    - Public subnets:
        * Direct internet access via Internet Gateway
        * Used for ALB and other public-facing resources
        * One subnet per specified AZ
        * CIDR ranges: 10.0.0.0/24, 10.0.2.0/24, etc.

    - Private subnets:
        * Internet access via NAT Gateway
        * Used for ECS tasks and RDS
        * One subnet per specified AZ
        * CIDR ranges: 10.0.1.0/24, 10.0.3.0/24, etc.

    Security Groups:
    - ALB Security Group:
        * Inbound: HTTP/HTTPS from internet
        * Outbound: All traffic

    - ECS Security Group:
        * Inbound: Traffic from ALB on service ports
        * Inbound: Inter-service communication
        * Outbound: All traffic

    - RDS Security Group:
        * Inbound: PostgreSQL port from VPC CIDR
        * Outbound: All traffic

    Attributes:
        vpc (Vpc): The main VPC resource
        public_subnets (List[Subnet]): List of public subnets
        private_subnets (List[Subnet]): List of private subnets
        alb_security_group (SecurityGroup): Security group for Application Load Balancer
        ecs_security_group (SecurityGroup): Security group for ECS tasks
        rds_security_group (SecurityGroup): Security group for RDS instances

    Parameters:
        scope (Construct): The scope in which this construct is defined
        id (str): The scoped construct ID
        project_prefix (str): Prefix for resource names (e.g., "project-name")
        vpc_cidr (str): CIDR block for the VPC (e.g., "10.0.0.0/16")
        vpc_subnet_azs (List[str]): List of AZs for subnet placement
        environment (str): Environment name (e.g., "prod", "dev")
        tags (dict): Tags to apply to all resources

    Example:
        ```python
        networking = NetworkingConstruct(
            self,
            "networking",
            project_prefix="myapp",
            vpc_cidr="10.0.0.0/16",
            vpc_subnet_azs=["us-east-1a", "us-east-1b"],
            environment="prod",
            tags={"Environment": "production"}
        )
        ```

    Notes:
        - NAT Gateway is created in first public subnet
        - Private subnets route through single NAT Gateway
        - VPC has DNS hostnames and DNS resolution enabled
        - Security groups follow least privilege principle
        - Subnet CIDR blocks are allocated sequentially
        - Resources tagged for cost allocation and management
        - Supports IPv4 networking
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
            domain="vpc",
            tags={**tags, "Name": f"{resource_prefix}-nat-eip"},
        )

        # Create subnets based on environment

        # For VPC CIDR 10.0.0.0/16, create subnets in 10.0.x.0/24 ranges
        for i, az in enumerate(vpc_subnet_azs):
            subnet_number = i * 2  # 0 for public subnet in dev

            # Public subnet
            public_subnet = Subnet(
                self,
                f"public-subnet-{i + 1}",
                vpc_id=self.vpc.id,
                cidr_block=f"10.0.{subnet_number}.0/24",
                availability_zone=az,
                map_public_ip_on_launch=True,
                tags={
                    **tags,
                    "Name": f"{resource_prefix}-public-subnet-{i + 1}",
                    "Type": "Public",
                },
            )
            self.public_subnets.append(public_subnet)

            # Associate public subnet with public route table
            RouteTableAssociation(
                self,
                f"public-rta-{i + 1}",
                subnet_id=public_subnet.id,
                route_table_id=public_route_table.id,
            )

            # Private subnet uses the next subnet number
            private_subnet = Subnet(
                self,
                f"private-subnet-{i + 1}",
                vpc_id=self.vpc.id,
                cidr_block=f"10.0.{subnet_number + 1}.0/24",
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
            ("stac-api", 8080, "STAC API from ALB"),
            ("stormlit", 8501, "Stormlit from ALB"),
            ("ecs-agent", 51678, "ECS Agent from ALB"),
            ("ecs-telemetry", 51679, "ECS Telemetry from ALB"),
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

        # RDS ingress rules - Allow traffic from the VPC
        SecurityGroupRule(
            self,
            "rds-vpc-ingress",
            type="ingress",
            security_group_id=self.rds_security_group.id,
            from_port=5432,
            to_port=5432,
            protocol="tcp",
            cidr_blocks=[vpc_cidr],
            description="Allow PostgreSQL access from VPC",
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
