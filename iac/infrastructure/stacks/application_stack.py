from typing import List
from constructs import Construct
from cdktf import TerraformOutput, TerraformVariable
from config import EnvironmentConfig
from .base_stack import BaseStack
from ..constructs.ecs_iam import EcsIamConstruct
from ..constructs.alb import AlbConstruct
from ..constructs.ecs_cluster import EcsClusterConstruct
from ..constructs.ecs_services import EcsServicesConstruct

from config import ServiceRoles


class ApplicationStack(BaseStack):
    """
    A stack that deploys the complete application infrastructure on AWS ECS.

    This stack orchestrates the deployment of a STAC API and Streamlit application using:
    1. ECS cluster with EC2 capacity providers
    2. Application Load Balancer for traffic distribution
    3. IAM roles and policies for ECS tasks
    4. CloudWatch log groups for monitoring
    5. Service discovery and networking configuration

    Application Components:
    - Streamlit Service:
        * Web interface for data visualization
        * S3 bucket access for data retrieval
        * Sticky sessions enabled
        * Custom container configuration

    - STAC API Service:
        * STAC FastAPI PGSTAC implementation
        * PostgreSQL database integration
        * Path-based routing (/stac/*)
        * Secure credentials management

    Infrastructure:
    - Load Balancer:
        * HTTPS termination
        * Path-based routing
        * Health checks
        * SSL/TLS certificates

    - ECS Cluster:
        * EC2 capacity providers
        * Auto-registration
        * CloudWatch integration
        * Task definitions

    Attributes:
        iam (EcsIamConstruct): IAM roles and policies
        ecs_cluster (EcsClusterConstruct): ECS cluster and instances
        alb (AlbConstruct): Application Load Balancer configuration

    Parameters:
        scope (Construct): The scope in which this stack is defined
        id (str): The scoped construct ID
        config (EnvironmentConfig): Environment configuration settings
        vpc_id (str): ID of the VPC for resource placement
        public_subnet_ids (List[str]): Public subnet IDs for ALB
        private_subnet_ids (List[str]): Private subnet IDs for ECS tasks
        alb_security_group_id (str): Security group ID for ALB
        ecs_security_group_id (str): Security group ID for ECS tasks
        rds_host (str): RDS instance hostname
        pgstac_read_secret_arn (str): ARN of PgSTAC read credentials secret

    Example:
        ```python
        app_stack = ApplicationStack(
            app,
            "myapp-prod-application",
            config,
            vpc_id=vpc.id,
            public_subnet_ids=["subnet-1", "subnet-2"],
            private_subnet_ids=["subnet-3", "subnet-4"],
            alb_security_group_id="sg-123",
            ecs_security_group_id="sg-456",
            rds_host="db.example.com",
            pgstac_read_secret_arn="arn:aws:secretsmanager:..."
        )
        ```

    Notes:
        - Services run in private subnets with NAT Gateway access
        - Container images pulled from GitHub Container Registry
        - Streamlit tag configurable via TF_VAR_stormlit_tag
        - Services depend on RDS database deployment
        - IAM roles follow least privilege principle
        - CloudWatch logs retained for 30 days
        - Load balancer DNS exported as stack output
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        config: EnvironmentConfig,
        *,
        vpc_id: str,
        public_subnet_ids: List[str],
        private_subnet_ids: List[str],
        alb_security_group_id: str,
        ecs_security_group_id: str,
        rds_host: str,
        pgstac_read_secret_arn: str,
    ) -> None:
        super().__init__(scope, id, config)

        stormlit_tag = (
            TerraformVariable(
                self,
                "stormlit_tag",
                type="string",
                description="Version tag for the stormlit image",
                default="latest",  # fallback to 'latest' if not provided
            ).string_value
            if config.ecs.stormlit_config.image_tag is None
            else config.ecs.stormlit_config.image_tag
        )

        config.ecs.stormlit_config.image_tag = stormlit_tag

        # Create IAM roles and instance profile
        self.iam = EcsIamConstruct(
            self,
            "ecs-iam",
            project_prefix=config.project_prefix,
            environment=config.environment,
            secret_arns=[
                pgstac_read_secret_arn,
            ],
            services={
                "streamlit": {
                    "task_role_statements": [
                        {
                            "Effect": "Allow",
                            "Action": [
                                "s3:GetObject",
                                "s3:ListBucket",
                            ],
                            "Resource": "*",
                        }
                    ],
                    "execution_role_statements": [],
                },
                "stac-api": {
                    "task_role_statements": [],
                    "execution_role_statements": [],
                    "secret_arns": [
                        pgstac_read_secret_arn,
                    ],
                },
            },
            tags=config.tags,
        )

        # Create ECS Cluster with EC2 instances
        self.ecs_cluster = EcsClusterConstruct(
            self,
            "ecs-cluster",
            project_prefix=config.project_prefix,
            environment=config.environment,
            instance_type=config.ecs.instance_type,
            instance_count=config.ecs.instance_count,
            subnet_ids=private_subnet_ids,
            security_group_id=ecs_security_group_id,
            instance_profile_name=self.iam.instance_profile.name,
            tags=config.tags,
        )

        # Create Application Load Balancer
        self.alb = AlbConstruct(
            self,
            "alb",
            project_prefix=config.project_prefix,
            environment=config.environment,
            app_config=config.application,
            vpc_id=vpc_id,
            public_subnet_ids=public_subnet_ids,
            security_group_id=alb_security_group_id,
            tags=config.tags,
        )

        # Create ECS Services (stac-api and stormlit)
        service_roles = {
            "stormlit": ServiceRoles(
                execution_role_arn=self.iam.service_execution_roles["streamlit"].arn,
                task_role_arn=self.iam.service_task_roles["streamlit"].arn,
            ),
            "stac-api": ServiceRoles(
                execution_role_arn=self.iam.service_execution_roles["stac-api"].arn,
                task_role_arn=self.iam.service_task_roles["stac-api"].arn,
            ),
        }

        # Create target groups mapping
        target_groups = {
            "stormlit": self.alb.app_target_group.arn,
            "stac-api": self.alb.stac_api_target_group.arn,
        }

        ecs_services = EcsServicesConstruct(
            self,
            "ecs-services",
            app_config=config.application,
            project_prefix=config.project_prefix,
            environment=config.environment,
            cluster_id=self.ecs_cluster.cluster.id,
            service_roles=service_roles,
            private_subnet_ids=private_subnet_ids,
            security_group_id=ecs_security_group_id,
            target_groups=target_groups,
            ecs_config=config.ecs,
            rds_host=rds_host,
            pgstac_read_secret_arn=pgstac_read_secret_arn,
            tags=config.tags,
        )

        # Add explicit dependencies
        ecs_services.node.add_dependency(self.alb)
        ecs_services.node.add_dependency(self.ecs_cluster)

        # Create outputs
        TerraformOutput(
            self,
            "alb-dns-name",
            value=self.alb.alb.dns_name,
            description="Application Load Balancer DNS Name",
        )

        TerraformOutput(
            self,
            "cluster-name",
            value=self.ecs_cluster.cluster.name,
            description="ECS Cluster Name",
        )
