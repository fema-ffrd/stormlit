import json
from typing import Dict, List, Optional
from constructs import Construct
from cdktf import FnGenerated
from cdktf_cdktf_provider_aws.ecs_task_definition import EcsTaskDefinition
from cdktf_cdktf_provider_aws.ecs_service import (
    EcsService,
    EcsServiceLoadBalancer,
    EcsServiceNetworkConfiguration,
)
from config import ServiceRoles, EcsConfig, EcsServiceConfig, ApplicationConfig


class EcsServicesConstruct(Construct):
    """
    A construct for deploying and configuring ECS services and task definitions.

    This construct manages the creation and configuration of ECS services for STAC API and Streamlit
    applications. It handles:
    1. Task definition creation with container configurations
    2. Service creation with load balancer integration
    3. Environment variable configuration
    4. Secret injection and management
    5. CloudWatch logs integration
    6. Network and security settings

    Service Configurations:
    - STAC API Service:
        * Runs the STAC FastAPI PGSTAC container
        * Configures PostgreSQL connection via secrets
        * Routes traffic through "/stac" path
        * Includes health checks and logging

    - Streamlit Service:
        * Runs the Streamlit application container
        * Configures STAC API endpoint integration
        * Manages session stickiness
        * Includes custom server settings

    Attributes:
        services (Dict[str, EcsService]): Map of service names to their ECS service resources

    Parameters:
        scope (Construct): The scope in which this construct is defined
        id (str): The scoped construct ID
        app_config (ApplicationConfig): Application configuration settings
        project_prefix (str): Prefix for resource names
        environment (str): Environment name (e.g., "prod", "dev")
        cluster_id (str): ECS cluster identifier
        service_roles (Dict[str, ServiceRoles]): IAM roles for each service
        private_subnet_ids (List[str]): Subnet IDs for service placement
        security_group_id (str): Security group ID for the services
        target_groups (Dict[str, str]): ALB target group ARNs for each service
        ecs_config (EcsConfig): Service-specific configurations
        rds_host (str): RDS instance hostname
        pgstac_admin_secret_arn (str): ARN of the PGSTAC admin credentials secret
        tags (dict): Tags to apply to all resources

    Example:
        ```python
        services = EcsServicesConstruct(
            self,
            "ecs-services",
            app_config=app_config,
            project_prefix="myapp",
            environment="prod",
            cluster_id=cluster.id,
            service_roles={
                "stormlit": ServiceRoles(
                    execution_role_arn="arn:aws:iam::...",
                    task_role_arn="arn:aws:iam::..."
                ),
                "stac-api": ServiceRoles(
                    execution_role_arn="arn:aws:iam::...",
                    task_role_arn="arn:aws:iam::..."
                )
            },
            private_subnet_ids=["subnet-1", "subnet-2"],
            security_group_id="sg-123",
            target_groups={
                "stormlit": "arn:aws:elasticloadbalancing:...",
                "stac-api": "arn:aws:elasticloadbalancing:..."
            },
            ecs_config=ecs_config,
            rds_host="db.example.com",
            pgstac_admin_secret_arn="arn:aws:secretsmanager:...",
            tags={"Environment": "production"}
        )
        ```

    Notes:
        - Services are deployed in private subnets with no public IPs
        - Load balancer target groups handle health checks and routing
        - Container logs are shipped to CloudWatch Logs
        - Secrets are injected as environment variables
        - Task definitions use awsvpc networking mode
        - Services support zero downtime deployments
        - Container resource limits are configurable via EcsConfig
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        app_config: ApplicationConfig,
        project_prefix: str,
        environment: str,
        cluster_id: str,
        service_roles: Dict[str, ServiceRoles],
        private_subnet_ids: List[str],
        security_group_id: str,
        target_groups: Dict[str, str],
        ecs_config: EcsConfig,
        rds_host: str,
        pgstac_admin_secret_arn: str,
        tags: dict,
    ) -> None:
        super().__init__(scope, id)

        self.resource_prefix = f"{project_prefix}-{environment}"
        self.services: Dict[str, EcsService] = {}

        # Create stormlit service
        if "stormlit" in service_roles:
            stormlit_container_definitions = [
                {
                    "name": "stormlit",
                    "image": f"{ecs_config.stormlit_config.image_repository}:{ecs_config.stormlit_config.image_tag}",
                    "cpu": ecs_config.stormlit_config.cpu,
                    "memory": ecs_config.stormlit_config.memory,
                    "essential": True,
                    "portMappings": [
                        {
                            "containerPort": ecs_config.stormlit_config.container_port,
                            "protocol": "tcp",
                        }
                    ],
                    "environment": [
                        {
                            "name": "STREAMLIT_SERVER_PORT",
                            "value": str(ecs_config.stormlit_config.container_port),
                        },
                        {"name": "STREAMLIT_SERVER_ADDRESS", "value": "0.0.0.0"},
                        {
                            "name": "STREAMLIT_BROWSER_GATHER_USAGE_STATS",
                            "value": "false",
                        },
                        {
                            "name": "STAC_API_URL",
                            "value": f"https://{app_config.stac_api_subdomain}.{app_config.domain_name}",
                        },
                        {
                            "name": "STAC_BROWSER_URL",
                            "value": "https://fema-ffrd.github.io/stac-browser",
                        },
                    ],
                    "logConfiguration": {
                        "logDriver": "awslogs",
                        "options": {
                            "awslogs-group": f"/ecs/{self.resource_prefix}-stormlit",
                            "awslogs-region": "us-east-1",
                            "awslogs-stream-prefix": "stormlit",
                            "awslogs-create-group": "true",
                        },
                    },
                }
            ]

            self.services["stormlit"] = self._create_service(
                "stormlit",
                stormlit_container_definitions,
                service_roles["stormlit"],
                target_groups.get("stormlit"),
                ecs_config.stormlit_config,
                cluster_id,
                private_subnet_ids,
                security_group_id,
                tags,
            )

        # Create STAC API service
        if "stac-api" in service_roles:
            stac_container_definitions = [
                {
                    "name": "stac-api",
                    "image": f"{ecs_config.stac_api_config.image_repository}:{ecs_config.stac_api_config.image_tag}",
                    "cpu": ecs_config.stac_api_config.cpu,
                    "memory": ecs_config.stac_api_config.memory,
                    "essential": True,
                    "portMappings": [
                        {
                            "containerPort": ecs_config.stac_api_config.container_port,
                            "protocol": "tcp",
                        }
                    ],
                    "secrets": [
                        {
                            "name": "POSTGRES_USER",
                            "valueFrom": f"{pgstac_admin_secret_arn}:username::",
                        },
                        {
                            "name": "POSTGRES_PASS",
                            "valueFrom": f"{pgstac_admin_secret_arn}:password::",
                        },
                    ],
                    "environment": [
                        {"name": "POSTGRES_HOST_READER", "value": rds_host or ""},
                        {"name": "POSTGRES_HOST_WRITER", "value": rds_host or ""},
                        {"name": "POSTGRES_PORT", "value": "5432"},
                        {"name": "POSTGRES_DBNAME", "value": "postgres"},
                    ],
                    "logConfiguration": {
                        "logDriver": "awslogs",
                        "options": {
                            "awslogs-group": f"/ecs/{self.resource_prefix}-stac-api",
                            "awslogs-region": "us-east-1",
                            "awslogs-stream-prefix": "stac-api",
                            "awslogs-create-group": "true",
                        },
                    },
                }
            ]

            self.services["stac-api"] = self._create_service(
                "stac-api",
                stac_container_definitions,
                service_roles["stac-api"],
                target_groups.get("stac-api"),
                ecs_config.stac_api_config,
                cluster_id,
                private_subnet_ids,
                security_group_id,
                tags,
            )

    def _create_service(
        self,
        service_name: str,
        container_definitions: List[dict],
        roles: ServiceRoles,
        target_group_arn: Optional[str],
        service_config: EcsServiceConfig,
        cluster_id: str,
        private_subnet_ids: List[str],
        security_group_id: str,
        tags: dict,
    ) -> EcsService:
        """
        Creates an ECS service with its task definition.
        """
        task_definition = EcsTaskDefinition(
            self,
            f"{service_name}-task-def",
            family=f"{self.resource_prefix}-{service_name}",
            requires_compatibilities=["EC2"],
            network_mode="awsvpc",
            cpu=str(service_config.cpu),
            memory=str(service_config.memory),
            execution_role_arn=roles.execution_role_arn,
            task_role_arn=roles.task_role_arn,
            container_definitions=json.dumps(container_definitions),
            tags=tags,
        )

        load_balancers = []
        if target_group_arn:
            load_balancers.append(
                EcsServiceLoadBalancer(
                    target_group_arn=target_group_arn,
                    container_name=service_name,
                    container_port=service_config.container_port,
                )
            )

        return EcsService(
            self,
            f"{service_name}-service",
            name=f"{self.resource_prefix}-{service_name}",
            cluster=cluster_id,
            task_definition=task_definition.arn,
            desired_count=service_config.container_count,
            launch_type="EC2",
            network_configuration=EcsServiceNetworkConfiguration(
                subnets=private_subnet_ids,
                security_groups=[security_group_id],
                assign_public_ip=False,
            ),
            load_balancer=load_balancers,
            tags=tags,
            deployment_minimum_healthy_percent=0,
            deployment_maximum_percent=100,
            deployment_circuit_breaker={
                "enable": False,
                "rollback": False,
            },
            health_check_grace_period_seconds=60,
            propagate_tags="SERVICE",
            force_new_deployment=True,
            triggers={
                "redeployment": FnGenerated.plantimestamp(),
            },
        )
