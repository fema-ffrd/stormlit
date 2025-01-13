from typing import List
from constructs import Construct
from cdktf import TerraformOutput, Token, TerraformVariable
from config import EnvironmentConfig
from .base_stack import BaseStack
from ..constructs.ecs_iam import EcsIamConstruct
from ..constructs.alb import AlbConstruct
from ..constructs.ecs_cluster import EcsClusterConstruct
from ..constructs.ecs_services import EcsServicesConstruct
from ..constructs.cloud_watch import CloudWatchConstruct


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
        rds_endpoint (str): The endpoint of the RDS database.

    Parameters:
        scope (Construct): The scope in which this stack is defined.
        id (str): A unique identifier for the stack.
        config (EnvironmentConfig): The environment configuration object containing project settings.
        vpc_id (str): The ID of the VPC to which this stack belongs.
        public_subnet_ids (List[str]): A list of IDs for public subnets.
        private_subnet_ids (List[str]): A list of IDs for private subnets.
        alb_security_group_id (str): The ID of the security group for the ALB.
        rds_endpoint (str): The endpoint of the RDS database to connect to.
        database_secret_arn (str): The ARN of the secret containing the database credentials.
        keycloak_secret_arn (str): The ARN of the secret containing the Keycloak credentials.
        streamlit_secret_arn (str): The ARN of the secret containing the Streamlit credentials.

    Methods:
        __init__(self, scope, id, config, vpc_id, public_subnet_ids, private_subnet_ids, alb_security_group_id,
            rds_endpoint): Initializes the application stack, setting up ECS, ECR, ALB, and other AWS resources.

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
        rds_endpoint: str,
        database_secret_arn: str,
        keycloak_secret_arn: str,
        streamlit_secret_arn: str,
        streamlit_repository_url: str,
        migration_repository_url: str,
    ) -> None:
        super().__init__(scope, id, config)

        streamlit_tag = TerraformVariable(
            self,
            "streamlit_tag",
            type="string",
            description="Version tag for the streamlit image",
            default="latest",  # fallback to 'latest' if not provided
        )

        migration_tag = TerraformVariable(
            self,
            "migration_tag",
            type="string",
            description="Version tag for the migration image",
            default="latest",  # fallback to 'latest' if not provided
        )

        # Create IAM roles and instance profile
        iam = EcsIamConstruct(
            self,
            "ecs-iam",
            project_prefix=config.project_prefix,
            environment=config.environment,
            secret_arns=[
                database_secret_arn,
                keycloak_secret_arn,
                streamlit_secret_arn,
            ],
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
        ecs_cluster = EcsClusterConstruct(
            self,
            "ecs-cluster",
            project_prefix=config.project_prefix,
            environment=config.environment,
            instance_type=config.ecs.instance_type,
            instance_count=config.ecs.instance_count,
            subnet_ids=private_subnet_ids,
            security_group_id=alb_security_group_id,
            instance_profile_name=iam.instance_profile.name,
            tags=config.tags,
        )

        # Create Application Load Balancer
        alb = AlbConstruct(
            self,
            "alb",
            project_prefix=config.project_prefix,
            environment=config.environment,
            vpc_id=vpc_id,
            public_subnet_ids=public_subnet_ids,
            security_group_id=alb_security_group_id,
            domain_name=config.application.domain_name,
            tags=config.tags,
        )

        # Create ECS Services (Keycloak and Streamlit)
        ecs_services = EcsServicesConstruct(
            self,
            "ecs-services",
            alb_dns_name=Token.as_string(alb.alb.dns_name),
            project_prefix=config.project_prefix,
            environment=config.environment,
            cluster_id=ecs_cluster.cluster.id,
            execution_role_arn=iam.execution_role.arn,
            task_role_arn=iam.task_role.arn,
            private_subnet_ids=private_subnet_ids,
            security_group_id=alb_security_group_id,
            keycloak_target_group_arn=alb.keycloak_target_group.arn,
            streamlit_target_group_arn=alb.streamlit_target_group.arn,
            keycloak_image=config.application.keycloak_image,
            streamlit_repository_url=streamlit_repository_url,
            streamlit_tag=streamlit_tag.string_value,
            migration_repository_url=migration_repository_url,
            migration_tag=migration_tag.string_value,
            rds_endpoint=rds_endpoint,
            database_secret_arn=database_secret_arn,
            keycloak_secret_arn=keycloak_secret_arn,
            streamlit_secret_arn=streamlit_secret_arn,
            streamlit_container_count=config.ecs.streamlit_container_count,
            tags=config.tags,
        )

        # Add explicit dependencies
        ecs_services.node.add_dependency(alb)
        ecs_services.node.add_dependency(ecs_cluster)

        # Create outputs
        TerraformOutput(
            self,
            "alb-dns-name",
            value=alb.alb.dns_name,
            description="Application Load Balancer DNS Name",
        )

        TerraformOutput(
            self,
            "db-init-task-definition-arn",
            value=ecs_services.db_init_task_definition.arn,
            description="Database Initialization Task Definition ARN",
        )

        TerraformOutput(
            self,
            "cluster-name",
            value=ecs_cluster.cluster.name,
            description="ECS Cluster Name",
        )
