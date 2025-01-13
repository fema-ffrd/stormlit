from typing import List
from constructs import Construct
from cdktf_cdktf_provider_aws.lb import Lb
from cdktf_cdktf_provider_aws.lb_listener import (
    LbListener,
    LbListenerDefaultAction,
)
from cdktf_cdktf_provider_aws.lb_listener_rule import (
    LbListenerRule,
    LbListenerRuleAction,
    LbListenerRuleCondition,
)
from cdktf_cdktf_provider_aws.lb_target_group import LbTargetGroup


class AlbConstruct(Construct):
    """
    A Construct for setting up an Application Load Balancer (ALB) with associated listeners, target groups,
    and routing rules.

    This construct simplifies the deployment and management of an Application Load Balancer (ALB) in AWS.
    It configures listeners, target groups, and routing rules to route traffic from the ALB to backend ECS services
    such as Keycloak and Streamlit. The ALB serves as a single entry point for incoming traffic and manages
    HTTP routing based on domain names.

    Attributes:
        alb (Lb): The Application Load Balancer resource.
        keycloak_target_group (LbTargetGroup): Target group for the Keycloak service.
        streamlit_target_group (LbTargetGroup): Target group for the Streamlit service.
        http_listener (LbListener): HTTP listener for the ALB.

    Parameters:
        scope (Construct): The scope in which this construct is defined.
        id (str): The unique identifier of the construct.
        project_prefix (str): A prefix for project-related resource names to ensure uniqueness.
        environment (str): The environment name (e.g., `production`, `staging`) to differentiate resources.
        vpc_id (str): The VPC ID where the ALB will be deployed.
        public_subnet_ids (List[str]): A list of public subnet IDs for ALB deployment.
        security_group_id (str): The security group ID for the ALB.
        domain_name (str): The base domain name for routing (e.g., `example.com`).
        tags (dict): A dictionary of tags to apply to all resources created by this construct.

    Methods:
        __init__(self, scope, id, ...): Initializes the ALB construct, creating the ALB, target groups, listeners,
            and routing rules for Keycloak and Streamlit applications.
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        project_prefix: str,
        environment: str,
        vpc_id: str,
        public_subnet_ids: List[str],
        security_group_id: str,
        domain_name: str,
        tags: dict,
    ) -> None:
        super().__init__(scope, id)

        resource_prefix = f"{project_prefix}-{environment}"

        # Create Application Load Balancer
        self.alb = Lb(
            self,
            "alb",
            name=f"{resource_prefix}-alb",
            internal=False,
            load_balancer_type="application",
            security_groups=[security_group_id],
            subnets=public_subnet_ids,
            enable_deletion_protection=True if environment == "production" else False,
            tags=tags,
        )

        # Create target groups for each service
        self.keycloak_target_group = LbTargetGroup(
            self,
            "keycloak-tg",
            name=f"{resource_prefix}-kc-tg",
            port=8080,
            protocol="HTTP",
            vpc_id=vpc_id,
            target_type="ip",
            health_check={
                "enabled": True,
                "healthy_threshold": 2,
                "interval": 30,
                "matcher": "302",
                "path": "/",
                "port": "traffic-port",
                "protocol": "HTTP",
                "timeout": 5,
                "unhealthy_threshold": 10,
            },
            tags=tags,
        )

        self.streamlit_target_group = LbTargetGroup(
            self,
            "streamlit-tg",
            name=f"{resource_prefix}-st-tg",
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
            stickiness={
                "enabled": True,
                "type": "app_cookie",
                "cookie_name": "streamlit_session",
                "cookie_duration": 86400,  # 24 hours
            },
            tags=tags,
        )

        # Create HTTP listener that forwards to Streamlit by default
        self.http_listener = LbListener(
            self,
            "http-listener",
            load_balancer_arn=self.alb.arn,
            port=80,
            protocol="HTTP",
            default_action=[
                LbListenerDefaultAction(
                    type="forward",
                    target_group_arn=self.streamlit_target_group.arn,
                )
            ],
            tags=tags,
        )

        # Create listener rule for Keycloak path
        LbListenerRule(
            self,
            "keycloak-rule",
            listener_arn=self.http_listener.arn,
            priority=1,
            condition=[
                LbListenerRuleCondition(
                    path_pattern={
                        "values": ["/auth/*"]
                    }
                )
            ],
            action=[
                LbListenerRuleAction(
                    type="forward",
                    target_group_arn=self.keycloak_target_group.arn,
                )
            ],
        )
