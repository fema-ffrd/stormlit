from typing import List
import json
from constructs import Construct
from cdktf import TerraformVariable, FnGenerated
from cdktf_cdktf_provider_aws.ecs_task_definition import EcsTaskDefinition
from config import EnvironmentConfig
from .base_stack import BaseStack
from cdktf_cdktf_provider_aws.ecs_service import (
    EcsService,
    EcsServiceLoadBalancer,
    EcsServiceNetworkConfiguration,
)
from cdktf_cdktf_provider_aws.lb_listener_rule import (
    LbListenerRule,
    LbListenerRuleAction,
    LbListenerRuleCondition,
)
from cdktf_cdktf_provider_aws.lb_target_group import LbTargetGroup


class ApplicationStackDev(BaseStack):
    """
    A stack to deploy the development streamlit container for testing and development purposes.
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        config: EnvironmentConfig,
        *,
        vpc_id: str,
        private_subnet_ids: List[str],
        security_group_id: str,
        alb_dns_name: str,
        execution_role_arn: str,
        task_role_arn: str,
        cluster_id: str,
        streamlit_repository_url: str,
        http_listener_arn: str,
        tags: dict,
    ) -> None:
        super().__init__(scope, id, config)

        resource_prefix = f"{config.project_prefix}-{config.environment}"

        streamlit_dev_tag = TerraformVariable(
            self,
            "streamlit_dev_tag",
            type="string",
            description="Version tag for the dev streamlit image",
            default="dev",  # fallback to 'dev' if not provided
        )

        # Create target group for Streamlit development server
        self.streamlit_dev_target_group = LbTargetGroup(
            self,
            "streamlit-dev-tg",
            name=f"{resource_prefix}-st-dev-tg",
            port=8501,
            protocol="HTTP",
            vpc_id=vpc_id,
            target_type="ip",
            health_check={
                "enabled": True,
                "healthy_threshold": 2,
                "interval": 30,
                "matcher": "200",
                "path": "/healthz",
                "port": "traffic-port",
                "protocol": "HTTP",
                "timeout": 5,
                "unhealthy_threshold": 10,
            },
            tags=tags,
        )

        # Create listener rule for Streamlit dev path
        LbListenerRule(
            self,
            "streamlit-dev-rule",
            listener_arn=http_listener_arn,
            priority=2,
            condition=[
                LbListenerRuleCondition(path_pattern={"values": ["/dev/*", "/dev"]})
            ],
            action=[
                LbListenerRuleAction(
                    type="forward",
                    target_group_arn=self.streamlit_dev_target_group.arn,
                )
            ],
        )

        streamlit_dev_container_definitions = [
            {
                "name": "streamlit-dev",
                "image": f"{streamlit_repository_url}:{streamlit_dev_tag}",
                "cpu": 512,
                "memory": 1024,
                "essential": True,
                "portMappings": [{"containerPort": 8501, "protocol": "tcp"}],
                "environment": [
                    {"name": "KEYCLOAK_URL", "value": f"{alb_dns_name}/auth"},
                    {"name": "STREAMLIT_SERVER_PORT", "value": "8501"},
                    {"name": "STREAMLIT_SERVER_ADDRESS", "value": "0.0.0.0"},
                    {"name": "STREAMLIT_SERVER_BASE_URL_PATH", "value": "/dev"},
                    {
                        "name": "STREAMLIT_BROWSER_GATHER_USAGE_STATS",
                        "value": "false",
                    },
                ],
                "logConfiguration": {
                    "logDriver": "awslogs",
                    "options": {
                        "awslogs-group": f"/ecs/{resource_prefix}-streamlit-dev",
                        "awslogs-region": "us-east-1",
                        "awslogs-stream-prefix": "streamlit-dev",
                        "awslogs-create-group": "true",
                    },
                },
            }
        ]
        streamlit_dev_task_definition = EcsTaskDefinition(
            self,
            "streamlit-dev-task-def",
            family=f"{resource_prefix}-streamlit-dev",
            requires_compatibilities=["EC2"],
            network_mode="awsvpc",
            cpu="512",
            memory="1024",
            execution_role_arn=execution_role_arn,
            task_role_arn=task_role_arn,
            container_definitions=json.dumps(streamlit_dev_container_definitions),
            tags=tags,
        )
        # Streamlit dev Service
        self.streamlit_dev_service = EcsService(
            self,
            "streamlit-dev-service",
            name=f"{resource_prefix}-streamlit-dev",
            cluster=cluster_id,
            task_definition=streamlit_dev_task_definition.arn,
            desired_count=1,
            launch_type="EC2",
            network_configuration=EcsServiceNetworkConfiguration(
                subnets=private_subnet_ids,
                security_groups=[security_group_id],
                assign_public_ip=False,
            ),
            load_balancer=[
                EcsServiceLoadBalancer(
                    target_group_arn=self.streamlit_dev_target_group.arn,
                    container_name="streamlit-dev",
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
            # Force a new deployment for each terraform apply
            force_new_deployment=True,
            triggers={
                "redeployment": FnGenerated.plantimestamp(),
            },
        )
