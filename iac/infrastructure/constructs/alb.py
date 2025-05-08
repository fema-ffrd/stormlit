import os
from typing import List
from constructs import Construct
from cdktf import TerraformOutput
from cdktf_cdktf_provider_aws.lb import Lb
from cdktf_cdktf_provider_aws.lb_listener import (
    LbListener,
    LbListenerDefaultAction,
    LbListenerDefaultActionAuthenticateOidc,
)
from cdktf_cdktf_provider_aws.lb_listener_certificate import LbListenerCertificate
from cdktf_cdktf_provider_aws.lb_target_group import LbTargetGroup
from .acm import AcmRoute53Construct
from config import ApplicationConfig


class AlbConstruct(Construct):
    """
    A construct for creating and configuring an Application Load Balancer (ALB).
    The ALB serves the Stormlit application with OIDC authentication.
    It also creates an ACM certificate for the STAC API domain (for API Gateway use)
    without creating an alias record for it.
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

        # Keycloak configuration from environment variables for Stormlit OIDC
        keycloak_issuer_url = os.getenv(
            "KEYCLOAK_ISSUER_URL", "http://localhost:8080/realms/your-realm"
        )
        keycloak_authorization_endpoint = os.getenv(
            "KEYCLOAK_AUTHORIZATION_ENDPOINT",
            f"{keycloak_issuer_url}/protocol/openid-connect/auth",
        )
        keycloak_token_endpoint = os.getenv(
            "KEYCLOAK_TOKEN_ENDPOINT",
            f"{keycloak_issuer_url}/protocol/openid-connect/token",
        )
        keycloak_user_info_endpoint = os.getenv(
            "KEYCLOAK_USER_INFO_ENDPOINT",
            f"{keycloak_issuer_url}/protocol/openid-connect/userinfo",
        )
        stormlit_keycloak_client_id = os.getenv("KEYCLOAK_CLIENT_ID", "stormlit")
        stormlit_keycloak_client_secret = os.getenv(
            "KEYCLOAK_CLIENT_SECRET", "stormlit-secret"
        )

        keycloak_oidc_scope = os.getenv("KEYCLOAK_OIDC_SCOPE", "openid profile email")
        keycloak_session_cookie_name = os.getenv(
            "KEYCLOAK_SESSION_COOKIE_NAME", "AWSELBAuthSessionCookieStormlit"
        )
        keycloak_session_timeout = int(os.getenv("KEYCLOAK_SESSION_TIMEOUT", "3600"))

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

        # ACM and Route53 for Stormlit frontend domain
        self.stormlit_acm_dns = AcmRoute53Construct(
            self,
            "stormlit-acm-dns",
            domain_name=app_config.domain_name,
            subdomain=app_config.stormlit_subdomain,
            tags=tags,
            create_alias_record=True,
            alias_target_dns_name=self.alb.dns_name,
            alias_target_zone_id=self.alb.zone_id,
        )
        self.stormlit_acm_dns.node.add_dependency(self.alb)

        # ACM certificate for STAC API domain (to be used by API Gateway)
        self.stac_api_certificate_only = AcmRoute53Construct(
            self,
            "stac-api-certificate-only",
            domain_name=app_config.domain_name,
            subdomain=app_config.stac_api_subdomain,
            tags=tags,
            create_alias_record=False,
        )
        self.stac_api_certificate_arn_for_apigw_output = TerraformOutput(
            self,
            "stac_api_certificate_arn_for_apigw",
            value=self.stac_api_certificate_only.certificate.arn,
            description="ARN of the ACM certificate for STAC API domain (to be used by API Gateway)",
        )
        self.app_domain_hosted_zone_id_output = TerraformOutput(
            self,
            "app_domain_hosted_zone_id",
            value=self.stormlit_acm_dns.hosted_zone.zone_id,
            description="Hosted Zone ID for the application's parent domain",
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
                "cookie_name": "streamlit_session_id",
                "cookie_duration": 86400,
            },
            tags=tags,
        )

        # OIDC configuration for Stormlit
        stormlit_oidc_auth_config = LbListenerDefaultActionAuthenticateOidc(
            issuer=keycloak_issuer_url,
            authorization_endpoint=keycloak_authorization_endpoint,
            token_endpoint=keycloak_token_endpoint,
            user_info_endpoint=keycloak_user_info_endpoint,
            client_id=stormlit_keycloak_client_id,
            client_secret=stormlit_keycloak_client_secret,
            scope=keycloak_oidc_scope,
            session_cookie_name=keycloak_session_cookie_name,
            session_timeout=keycloak_session_timeout,
        )

        # Create HTTPS listener with OIDC for Stormlit as default
        self.https_listener = LbListener(
            self,
            "https-listener",
            load_balancer_arn=self.alb.arn,
            port=443,
            protocol="HTTPS",
            ssl_policy="ELBSecurityPolicy-2016-08",
            certificate_arn=self.stormlit_acm_dns.certificate.arn,
            default_action=[
                LbListenerDefaultAction(
                    type="authenticate-oidc",
                    authenticate_oidc=stormlit_oidc_auth_config,
                    order=1,
                ),
                LbListenerDefaultAction(
                    type="forward", target_group_arn=self.app_target_group.arn, order=2
                ),
            ],
            tags=tags,
        )

        LbListenerCertificate(
            self,
            "stac-api-cert-on-alb-listener",
            listener_arn=self.https_listener.arn,
            certificate_arn=self.stac_api_certificate_only.certificate.arn,
        )

        self.https_listener.node.add_dependency(
            self.stormlit_acm_dns.certificate_validation
        )
        self.https_listener.node.add_dependency(
            self.stac_api_certificate_only.certificate_validation
        )

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

        # Output ALB DNS name and zone ID
        self.alb_dns_name_output = TerraformOutput(
            self,
            "alb_dns_name",
            value=self.alb.dns_name,
            description="The DNS name of the Application Load Balancer",
        )
        self.alb_zone_id_output = TerraformOutput(
            self,
            "alb_zone_id",
            value=self.alb.zone_id,
            description="The hosted zone ID of the Application Load Balancer",
        )
        self.https_listener_arn_output = TerraformOutput(
            self,
            "https_listener_arn",
            value=self.https_listener.arn,
            description="The ARN of the HTTPS listener",
        )
