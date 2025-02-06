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
from config import ApplicationConfig


class AlbConstruct(Construct):
    """
    A construct for creating and configuring an Application Load Balancer (ALB) with HTTPS support.

    This construct manages the creation of an Application Load Balancer and its associated resources:
    1. Creates an Application Load Balancer in public subnets
    2. Sets up HTTPS listener with TLS termination using ACM certificate
    3. Creates an HTTP listener that redirects to HTTPS
    4. Configures target groups for different services
    5. Sets up listener rules for path-based routing
    6. Manages DNS and SSL certificate configuration through ACM and Route53

    The ALB is configured with:
    - Dual stack listeners (HTTP on port 80, HTTPS on port 443)
    - Automatic HTTP to HTTPS redirection
    - Path-based routing for different backend services
    - Support for sticky sessions on app target group
    - Health checks for each target group
    - Integration with ACM for SSL/TLS certificates

    Attributes:
        alb (Lb): The Application Load Balancer resource
        acm (AcmRoute53Construct): The ACM and Route53 configuration for SSL/TLS
        stac_api_target_group (LbTargetGroup): Target group for STAC API service
        app_target_group (LbTargetGroup): Target group for Streamlit application
        https_listener (LbListener): The HTTPS listener (port 443)
        http_listener (LbListener): The HTTP listener (port 80, redirects to HTTPS)

    Parameters:
        scope (Construct): The scope in which this construct is defined
        id (str): The scoped construct ID
        project_prefix (str): Prefix for resource names (e.g., "project-name")
        environment (str): Environment name (e.g., "prod", "dev")
        app_config (ApplicationConfig): Application configuration including domain settings
        vpc_id (str): The ID of the VPC where the ALB will be created
        public_subnet_ids (List[str]): List of public subnet IDs for ALB placement
        security_group_id (str): Security group ID for the ALB
        tags (dict): Tags to apply to all resources

    Example:
        ```python
        alb = AlbConstruct(
            self,
            "alb",
            project_prefix="myapp",
            environment="prod",
            app_config=app_config,
            vpc_id=vpc.id,
            public_subnet_ids=["subnet-1", "subnet-2"],
            security_group_id="sg-123",
            tags={"Environment": "production"}
        )
        ```

    Notes:
        - The ALB is created in public subnets to be accessible from the internet
        - Health check settings are configured separately for each target group
        - The app target group uses cookie-based stickiness for session management
        - STAC API requests are routed based on the "/stac" path prefix
        - All other requests are routed to the app target group
        - SSL certificates are automatically provisioned and validated through ACM
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        project_prefix: str,
        environment: str,
        app_config: ApplicationConfig,
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
            enable_deletion_protection=app_config.enable_deletion_protection,
            tags=tags,
        )

        # Create ACM certificate and Route53 records
        self.acm = AcmRoute53Construct(
            self,
            "acm",
            domain_name=app_config.domain_name,
            subdomain=app_config.subdomain,
            alb_dns_name=self.alb.dns_name,
            alb_zone_id=self.alb.zone_id,
            tags=tags,
        )

        self.acm.node.add_dependency(self.alb)

        # Create target groups for each service
        self.stac_api_target_group = LbTargetGroup(
            self,
            "stac-api-tg",
            name=f"{resource_prefix}-stac-api-tg",
            port=8080,
            protocol="HTTP",
            vpc_id=vpc_id,
            target_type="ip",
            health_check={
                "enabled": True,
                "healthy_threshold": 2,
                "interval": 30,
                "matcher": "200",
                "path": "/",
                "port": "traffic-port",
                "protocol": "HTTP",
                "timeout": 5,
                "unhealthy_threshold": 10,
            },
            tags=tags,
        )

        self.app_target_group = LbTargetGroup(
            self,
            "app-tg",
            name=f"{resource_prefix}-app-tg",
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
                    target_group_arn=self.app_target_group.arn,
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

        # Create listener rule for stac api path
        LbListenerRule(
            self,
            "stac-api-rule",
            listener_arn=self.https_listener.arn,
            priority=1,
            condition=[
                LbListenerRuleCondition(path_pattern={"values": ["/stac/*", "/stac"]})
            ],
            action=[
                LbListenerRuleAction(
                    type="forward",
                    target_group_arn=self.stac_api_target_group.arn,
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
