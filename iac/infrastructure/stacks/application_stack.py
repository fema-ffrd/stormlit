from typing import List
from constructs import Construct
from cdktf import TerraformOutput, TerraformVariable
from config import EnvironmentConfig
from .base_stack import BaseStack
from ..constructs.ecs_iam import EcsIamConstruct
from ..constructs.alb import AlbConstruct
from ..constructs.ecs_cluster import EcsClusterConstruct
from ..constructs.ecs_services import EcsServicesConstruct
from ..constructs.cloud_watch import CloudWatchConstruct

from config import ServiceRoles


class ApplicationStack(BaseStack):
    """
    A stack to deploy an AWS application environment, including ECS, ECR, ALB, and associated IAM roles and services.

    This stack orchestrates the creation of critical AWS resources like ECS clusters, ECR repositories, ALB,
    CloudWatch, and IAM roles, configuring them to ensure seamless communication and monitoring. It establishes
    ECS services for applications like Keycloak and Streamlit, integrates RDS, and handles networking resources
    like VPCs and subnets. The stack also manages dependencies between ECS services, ensuring that all components
    are deployed in the correct sequence.

    Attributes:
        ecs_services (EcsServicesConstruct): The ECS services construct managing Keycloak and Streamlit.
        ecs_cluster (EcsClusterConstruct): The ECS cluster constructed for EC2 instances.
        alb (AlbConstruct): The Application Load Balancer construct.
        cloudwatch (CloudWatchConstruct): The CloudWatch construct for logging and monitoring.
        ecr (EcrConstruct): The ECR repository construct for container images.
        iam (EcsIamConstruct): The IAM roles and instance profiles for ECS services.
        rds_host (str): The endpoint of the RDS database.

    Parameters:
        scope (Construct): The scope in which this stack is defined.
        id (str): A unique identifier for the stack.
        config (EnvironmentConfig): The environment configuration object containing project settings.
        vpc_id (str): The ID of the VPC to which this stack belongs.
        public_subnet_ids (List[str]): A list of IDs for public subnets.
        private_subnet_ids (List[str]): A list of IDs for private subnets.
        alb_security_group_id (str): The ID of the security group for the ALB.
        rds_host (str): The endpoint of the RDS database to connect to.
        database_secret_arn (str): The ARN of the secret containing the database credentials.
        keycloak_secret_arn (str): The ARN of the secret containing the Keycloak credentials.
        streamlit_secret_arn (str): The ARN of the secret containing the Streamlit credentials.

    Methods:
        __init__(self, scope, id, config, vpc_id, public_subnet_ids, private_subnet_ids, alb_security_group_id,
            rds_host): Initializes the application stack, setting up ECS, ECR, ALB, and other AWS resources.

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

        # Create CloudWatch Log Groups
        CloudWatchConstruct(
            self,
            "cloudwatch",
            project_prefix=config.project_prefix,
            environment=config.environment,
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
            host_name=f"{config.application.subdomain}.{config.application.domain_name}",
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
