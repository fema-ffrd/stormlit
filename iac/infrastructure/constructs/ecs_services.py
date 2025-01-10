import json
from typing import List
from constructs import Construct
from cdktf_cdktf_provider_aws.ecs_task_definition import EcsTaskDefinition
from cdktf_cdktf_provider_aws.ecs_service import (
    EcsService,
    EcsServiceLoadBalancer,
    EcsServiceNetworkConfiguration,
)


class EcsServicesConstruct(Construct):
    """
    A Construct for defining ECS services for Keycloak and Streamlit applications.

    This construct simplifies the deployment of ECS services for two critical components:
    Keycloak and Streamlit. It sets up ECS task definitions, services, and related configurations.

    Attributes:
        keycloak_service (EcsService): The ECS service responsible for running the Keycloak application.
        streamlit_service (EcsService): The ECS service responsible for running the Streamlit application.

    Parameters:
        scope (Construct): The scope in which this construct is defined.
        id (str): The unique identifier of the construct.
        alb_dns_name (str): The DNS name of the Application Load Balancer for routing traffic.
        project_prefix (str): A prefix for project-related resource names to ensure uniqueness.
        environment (str): The environment name (e.g., `production`, `staging`) to differentiate resources.
        cluster_id (str): The ECS cluster identifier where services will be deployed.
        execution_role_arn (str): The ARN of the IAM execution role for ECS tasks.
        task_role_arn (str): The ARN of the IAM task role for ECS tasks.
        private_subnet_ids (List[str]): A list of private subnet IDs where the ECS services will be deployed.
        security_group_id (str): The ID of the security group to associate with ECS services.
        keycloak_target_group_arn (str): The ARN of the AWS Application Load Balancer target group for Keycloak.
        streamlit_target_group_arn (str): The ARN of the AWS Application Load Balancer target group for Streamlit.
        keycloak_image (str): The Docker image URI for the Keycloak application.
        streamlit_repository_url (str): The URL of the ECR repository for the Streamlit application.
        streamlit_tag (str): The tag of the Streamlit Docker image to deploy.
        rds_endpoint (str): The endpoint of the RDS database for storing application data.
        keycloak_admin_user (str): The Keycloak admin user for initial setup.
        keycloak_admin_password (str): The Keycloak admin password for initial setup.
        streamlit_container_count (int): The desired number of Streamlit container instances.
        tags (dict): A dictionary of tags to apply to all resources created by this construct.

    Methods:
        __init__(self, scope, id, ...): Initializes the ECS services construct, creating necessary ECS task definitions
            and services for Keycloak and Streamlit.
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        alb_dns_name: str,
        project_prefix: str,
        environment: str,
        cluster_id: str,
        execution_role_arn: str,
        task_role_arn: str,
        private_subnet_ids: List[str],
        security_group_id: str,
        keycloak_target_group_arn: str,
        streamlit_target_group_arn: str,
        keycloak_image: str,
        streamlit_repository_url: str,
        streamlit_tag: str,
        rds_endpoint: str,
        database_secret_arn: str,
        keycloak_secret_arn: str,
        streamlit_secret_arn: str,
        streamlit_container_count: int,
        tags: dict,
    ) -> None:
        super().__init__(scope, id)

        resource_prefix = f"{project_prefix}-{environment}"

        # Keycloak Task Definition
        keycloak_container_definitions = [
            {
                "name": "keycloak",
                "image": keycloak_image,
                "cpu": 512,
                "memory": 1024,
                "essential": True,
                "portMappings": [
                    {"containerPort": 8080, "hostPort": 8080, "protocol": "tcp"},
                    {"containerPort": 9000, "hostPort": 9000, "protocol": "tcp"},
                ],
                "entryPoint": ["/opt/keycloak/bin/kc.sh"],
                "command": ["start"],  # Using production mode
                "secrets": [
                    {
                        "name": "KC_DB_USERNAME",
                        "valueFrom": f"{database_secret_arn}:username::",
                    },
                    {
                        "name": "KC_DB_PASSWORD",
                        "valueFrom": f"{database_secret_arn}:password::",
                    },
                    {
                        "name": "KEYCLOAK_ADMIN",
                        "valueFrom": f"{keycloak_secret_arn}:admin_user::",
                    },
                    {
                        "name": "KEYCLOAK_ADMIN_PASSWORD",
                        "valueFrom": f"{keycloak_secret_arn}:admin_password::",
                    },
                ],
                "environment": [
                    {"name": "KC_DB", "value": "postgres"},
                    {
                        "name": "KC_DB_URL",
                        "value": f"jdbc:postgresql://{rds_endpoint}/keycloak",
                    },
                    {"name": "KC_HEALTH_ENABLED", "value": "true"},
                    {"name": "KC_METRICS_ENABLED", "value": "true"},
                    {"name": "KC_HTTP_ENABLED", "value": "true"},
                    {"name": "KC_PROXY", "value": "edge"},
                    {"name": "KC_HOSTNAME_STRICT", "value": "false"},
                    {"name": "KC_HOSTNAME_STRICT_HTTPS", "value": "false"},
                    {
                        "name": "JAVA_OPTS_APPEND",
                        "value": "-XX:MaxRAMPercentage=75 -XX:InitialRAMPercentage=50",
                    },
                    {
                        "name": "KC_HTTP_RELATIVE_PATH",
                        "value": "/auth"
                    },
                    {
                        "name": "KC_HOSTNAME_STRICT",
                        "value": "false"
                    },
                    {
                        "name": "KC_HOSTNAME_STRICT_HTTPS",
                        "value": "false"
                    },
                ],
                "logConfiguration": {
                    "logDriver": "awslogs",
                    "options": {
                        "awslogs-group": f"/ecs/{resource_prefix}-keycloak",
                        "awslogs-region": tags.get("Region", "us-east-2"),
                        "awslogs-stream-prefix": "keycloak",
                        "awslogs-create-group": "true",
                    },
                }
            }
        ]

        keycloak_task_definition = EcsTaskDefinition(
            self,
            "keycloak-task-def",
            family=f"{resource_prefix}-keycloak",
            requires_compatibilities=["EC2"],
            network_mode="awsvpc",
            cpu="512",
            memory="1024",
            execution_role_arn=execution_role_arn,
            task_role_arn=task_role_arn,
            container_definitions=json.dumps(keycloak_container_definitions),
            tags=tags,
        )

        # Keycloak Service
        self.keycloak_service = EcsService(
            self,
            "keycloak-service",
            name=f"{resource_prefix}-keycloak",
            cluster=cluster_id,
            task_definition=keycloak_task_definition.arn,
            desired_count=1,  # Keycloak always runs as a single instance
            launch_type="EC2",
            network_configuration=EcsServiceNetworkConfiguration(
                subnets=private_subnet_ids,
                security_groups=[security_group_id],
                assign_public_ip=False,
            ),
            load_balancer=[
                EcsServiceLoadBalancer(
                    target_group_arn=keycloak_target_group_arn,
                    container_name="keycloak",
                    container_port=8080,
                ),
            ],
            tags=tags,
            deployment_minimum_healthy_percent=0,  # Allow all tasks to be stopped during deployment
            deployment_maximum_percent=100,  # Don't allow more than the desired count during deployment
            deployment_circuit_breaker={
                "enable": False,
                "rollback": False,
            },
            health_check_grace_period_seconds=120,
            propagate_tags="SERVICE",
        )

        # Streamlit Task Definition
        streamlit_container_definitions = [
            {
                "name": "streamlit",
                "image": f"{streamlit_repository_url}:{streamlit_tag}",
                "cpu": 1024,
                "memory": 1500,
                "essential": True,
                "portMappings": [
                    {"containerPort": 8501, "hostPort": 8501, "protocol": "tcp"}
                ],
                "secrets": [
                    {
                        "name": "DB_USERNAME",
                        "valueFrom": f"{streamlit_secret_arn}:admin_user::",
                    },
                    {
                        "name": "DB_PASSWORD",
                        "valueFrom": f"{streamlit_secret_arn}:admin_password::",
                    },
                ],
                "environment": [
                    {
                        "name": "DB_HOST",
                        "value": rds_endpoint,
                    },
                    {
                        "name": "DB_NAME",
                        "value": "streamlit",
                    },
                    {"name": "KEYCLOAK_URL", "value": f"{alb_dns_name}/auth"},
                    {"name": "STREAMLIT_SERVER_PORT", "value": "8501"},
                    {"name": "STREAMLIT_SERVER_ADDRESS", "value": "0.0.0.0"},
                    {"name": "STREAMLIT_BROWSER_GATHER_USAGE_STATS", "value": "false"},
                ],
                "logConfiguration": {
                    "logDriver": "awslogs",
                    "options": {
                        "awslogs-group": f"/ecs/{resource_prefix}-streamlit",
                        "awslogs-region": tags.get("Region", "us-east-2"),
                        "awslogs-stream-prefix": "streamlit",
                        "awslogs-create-group": "true",
                    },
                }
            }
        ]

        streamlit_task_definition = EcsTaskDefinition(
            self,
            "streamlit-task-def",
            family=f"{resource_prefix}-streamlit",
            requires_compatibilities=["EC2"],
            network_mode="awsvpc",
            cpu="1024",
            memory="1500",
            execution_role_arn=execution_role_arn,
            task_role_arn=task_role_arn,
            container_definitions=json.dumps(streamlit_container_definitions),
            tags=tags,
        )

        # Streamlit Service
        self.streamlit_service = EcsService(
            self,
            "streamlit-service",
            name=f"{resource_prefix}-streamlit",
            cluster=cluster_id,
            task_definition=streamlit_task_definition.arn,
            desired_count=streamlit_container_count,
            launch_type="EC2",
            network_configuration=EcsServiceNetworkConfiguration(
                subnets=private_subnet_ids,
                security_groups=[security_group_id],
                assign_public_ip=False,
            ),
            load_balancer=[
                EcsServiceLoadBalancer(
                    target_group_arn=streamlit_target_group_arn,
                    container_name="streamlit",
                    container_port=8501,
                )
            ],
            tags=tags,
            deployment_minimum_healthy_percent=0,  # Allow all tasks to be stopped during deployment
            deployment_maximum_percent=100,  # Don't allow more than the desired count during deployment
            deployment_circuit_breaker={
                "enable": False,
                "rollback": False,
            },
            health_check_grace_period_seconds=60,
            propagate_tags="SERVICE",
        )
