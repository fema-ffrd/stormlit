import json
import os
from typing import Dict, List, Optional
from constructs import Construct
from cdktf import FnGenerated
from cdktf_cdktf_provider_aws.service_discovery_http_namespace import (
    ServiceDiscoveryHttpNamespace,
)
from cdktf_cdktf_provider_aws.ecs_task_definition import EcsTaskDefinition
from cdktf_cdktf_provider_aws.ecs_service import (
    EcsService,
    EcsServiceLoadBalancer,
    EcsServiceNetworkConfiguration,
    EcsServiceServiceConnectConfiguration,
    EcsServiceServiceConnectConfigurationService,
    EcsServiceServiceConnectConfigurationServiceClientAlias,
)
from config import ServiceRoles, EcsConfig, EcsServiceConfig, ApplicationConfig


class EcsServicesConstruct(Construct):
    """
    A construct for deploying and configuring ECS services and task definitions.
    Stormlit service is configured with ALB.
    STAC API service is configured to be fronted by an NLB.
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        app_config: ApplicationConfig,
        region: str,
        project_prefix: str,
        environment: str,
        cluster_id: str,
        cluster_name: str,
        service_roles: Dict[str, ServiceRoles],
        private_subnet_ids: List[str],
        security_group_id: str,
        stormlit_alb_target_group_arn: str,
        stac_api_nlb_target_group_arn: str,
        ecs_config: EcsConfig,
        rds_host: str,
        pgstac_admin_secret_arn: str,
        tags: dict,
        vpc_id: str,
    ) -> None:
        super().__init__(scope, id)

        self.resource_prefix = f"{project_prefix}-{environment}"
        self.services: Dict[str, EcsService] = {}

        current_region = region

        # Create a CloudMap HTTP namespace for Service Connect
        self.service_connect_namespace = ServiceDiscoveryHttpNamespace(
            self,
            "service-connect-namespace",
            name=f"{self.resource_prefix}-namespace",
            description=f"Namespace for {self.resource_prefix} Service Connect services",
            tags=tags,
        )

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
                            "name": "stormlit-http",
                        }
                    ],
                    "secrets": [
                        {
                            "name": "PG_USER",
                            "valueFrom": f"{pgstac_admin_secret_arn}:username::",
                        },
                        {
                            "name": "PG_PASS",
                            "valueFrom": f"{pgstac_admin_secret_arn}:password::",
                        },
                        {
                            "name": "AWS_ACCESS_KEY_ID",
                            "value": f"{os.getenv('AWS_ACCESS_KEY_ID', 'stormtlit-secret')}",
                        },
                        {
                            "name": "AWS_SECRET_ACCESS_KEY",
                            "valueFrom": f"{os.getenv('AWS_SECRET_ACCESS_KEY', 'stormlit-secret')}",
                        },
                    ],
                    "environment": [
                        {
                            "name": "AWS_REGION",
                            "value": current_region,
                        },
                        {"name": "PG_HOST", "value": rds_host or ""},
                        {"name": "PG_PORT", "value": "5432"},
                        {"name": "PG_DBNAME", "value": "postgres"},
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
                            "awslogs-region": current_region,
                            "awslogs-stream-prefix": "stormlit",
                            "awslogs-create-group": "true",
                        },
                    },
                }
            ]

            stormlit_load_balancers = []
            if stormlit_alb_target_group_arn:
                stormlit_load_balancers.append(
                    EcsServiceLoadBalancer(
                        target_group_arn=stormlit_alb_target_group_arn,
                        container_name="stormlit",
                        container_port=ecs_config.stormlit_config.container_port,
                    )
                )

            self.services["stormlit"] = self._create_service(
                service_name="stormlit",
                container_definitions=stormlit_container_definitions,
                roles=service_roles["stormlit"],
                service_config=ecs_config.stormlit_config,
                cluster_id=cluster_id,
                private_subnet_ids=private_subnet_ids,
                security_group_id=security_group_id,
                tags=tags,
                load_balancers=stormlit_load_balancers,
                enable_service_connect=False,
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
                            "name": "stac-api-http",
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
                        {"name": "ROOT_PATH", "value": ""},
                        {"name": "CORS_ORIGIN", "value": "*"},
                        {"name": "CORS_METHODS", "value": "*"},
                    ],
                    "logConfiguration": {
                        "logDriver": "awslogs",
                        "options": {
                            "awslogs-group": f"/ecs/{self.resource_prefix}-stac-api",
                            "awslogs-region": current_region,
                            "awslogs-stream-prefix": "stac-api",
                            "awslogs-create-group": "true",
                        },
                    },
                }
            ]

            stac_api_load_balancers = []
            if stac_api_nlb_target_group_arn:
                stac_api_load_balancers.append(
                    EcsServiceLoadBalancer(
                        target_group_arn=stac_api_nlb_target_group_arn,
                        container_name="stac-api",
                        container_port=ecs_config.stac_api_config.container_port,
                    )
                )

            self.services["stac-api"] = self._create_service(
                service_name="stac-api",
                container_definitions=stac_container_definitions,
                roles=service_roles["stac-api"],
                service_config=ecs_config.stac_api_config,
                cluster_id=cluster_id,
                private_subnet_ids=private_subnet_ids,
                security_group_id=security_group_id,
                tags=tags,
                load_balancers=stac_api_load_balancers,
                enable_service_connect=True,
                service_connect_service_name="stac-api-svc",
                service_connect_port_name="stac-api-http",
            )

    def _create_service(
        self,
        service_name: str,
        container_definitions: List[dict],
        roles: ServiceRoles,
        service_config: EcsServiceConfig,
        cluster_id: str,
        private_subnet_ids: List[str],
        security_group_id: str,
        tags: dict,
        load_balancers: Optional[List[EcsServiceLoadBalancer]] = None,
        enable_service_connect: bool = False,
        service_connect_service_name: Optional[str] = None,
        service_connect_port_name: Optional[str] = None,
    ) -> EcsService:
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

        service_connect_config = None
        if (
            enable_service_connect
            and service_connect_service_name
            and service_connect_port_name
        ):
            service_connect_config = EcsServiceServiceConnectConfiguration(
                enabled=True,
                namespace=self.service_connect_namespace.name,
                service=[
                    EcsServiceServiceConnectConfigurationService(
                        port_name=service_connect_port_name,
                        discovery_name=service_connect_service_name,
                        client_alias=EcsServiceServiceConnectConfigurationServiceClientAlias(
                            port=service_config.container_port,
                            dns_name=service_connect_service_name,
                        ),
                    )
                ],
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
            load_balancer=load_balancers if load_balancers else [],
            service_connect_configuration=service_connect_config,
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
                "redeployment_trigger": FnGenerated.plantimestamp(),
            },
            depends_on=[task_definition],
        )
