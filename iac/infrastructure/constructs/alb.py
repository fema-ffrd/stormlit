from typing import List
from constructs import Construct
from cdktf import TerraformOutput
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
from .acm import AcmRoute53Construct


class AlbConstruct(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        project_prefix: str,
        environment: str,
        domain_name: str,
        vpc_id: str,
        public_subnet_ids: List[str],
        security_group_id: str,
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

        # Create ACM certificate and Route53 records
        self.acm = AcmRoute53Construct(
            self,
            "acm",
            domain_name=domain_name,
            subdomain="stormlit",
            alb_dns_name=self.alb.dns_name,
            alb_zone_id=self.alb.zone_id,
            tags=tags,
        )

        self.acm.node.add_dependency(self.alb)

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

        # Create HTTPS listener that forwards to Streamlit by default
        self.https_listener = LbListener(
            self,
            "https-listener",
            load_balancer_arn=self.alb.arn,
            port=443,
            protocol="HTTPS",
            ssl_policy="ELBSecurityPolicy-2016-08",
            certificate_arn=self.acm.certificate.arn,
            default_action=[
                LbListenerDefaultAction(
                    type="forward",
                    target_group_arn=self.streamlit_target_group.arn,
                )
            ],
            tags=tags,
        )

        self.https_listener.node.add_dependency(self.acm.certificate_validation)

        # Create HTTP listener that redirects to HTTPS
        self.http_listener = LbListener(
            self,
            "http-listener",
            load_balancer_arn=self.alb.arn,
            port=80,
            protocol="HTTP",
            default_action=[
                LbListenerDefaultAction(
                    type="redirect",
                    redirect={
                        "port": "443",
                        "protocol": "HTTPS",
                        "status_code": "HTTP_301",
                    },
                )
            ],
            tags=tags,
        )

        # Create listener rule for Keycloak path
        LbListenerRule(
            self,
            "keycloak-rule",
            listener_arn=self.https_listener.arn,
            priority=1,
            condition=[
                LbListenerRuleCondition(path_pattern={"values": ["/auth/*", "/auth"]})
            ],
            action=[
                LbListenerRuleAction(
                    type="forward",
                    target_group_arn=self.keycloak_target_group.arn,
                )
            ],
        )

        # Output ALB DNS name and zone ID
        TerraformOutput(
            self,
            "alb-dns-name",
            value=self.alb.dns_name,
            description="The DNS name of the Application Load Balancer",
        )

        TerraformOutput(
            self,
            "alb-zone-id",
            value=self.alb.zone_id,
            description="The hosted zone ID of the Application Load Balancer",
        )

        TerraformOutput(
            self,
            "https-listener-arn",
            value=self.https_listener.arn,
            description="The ARN of the HTTPS listener",
        )
