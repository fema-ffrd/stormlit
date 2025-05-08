import os
from typing import List, Dict
from constructs import Construct
from cdktf import TerraformOutput
from cdktf_cdktf_provider_aws.apigatewayv2_api import Apigatewayv2Api
from cdktf_cdktf_provider_aws.apigatewayv2_authorizer import Apigatewayv2Authorizer, Apigatewayv2AuthorizerJwtConfiguration
from cdktf_cdktf_provider_aws.apigatewayv2_integration import Apigatewayv2Integration
from cdktf_cdktf_provider_aws.apigatewayv2_route import Apigatewayv2Route
from cdktf_cdktf_provider_aws.apigatewayv2_stage import Apigatewayv2Stage
from cdktf_cdktf_provider_aws.apigatewayv2_vpc_link import Apigatewayv2VpcLink
from cdktf_cdktf_provider_aws.apigatewayv2_domain_name import Apigatewayv2DomainName, Apigatewayv2DomainNameDomainNameConfiguration
from cdktf_cdktf_provider_aws.apigatewayv2_api_mapping import Apigatewayv2ApiMapping
from cdktf_cdktf_provider_aws.route53_record import Route53Record
from cdktf_cdktf_provider_aws.lb import Lb as Nlb
from cdktf_cdktf_provider_aws.lb_target_group import LbTargetGroup as NlbTargetGroup
from cdktf_cdktf_provider_aws.lb_listener import LbListener, LbListenerDefaultAction
from config import ApplicationConfig, EcsServiceConfig


class ApiGatewayConstruct(Construct):
    """
    A construct for creating an API Gateway (HTTP API) with JWT authentication
    for the STAC API, integrated with an ECS service via an NLB and VPC Link.
    Includes custom domain configuration.
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
        private_subnet_ids: List[str],
        stac_service_config: EcsServiceConfig,
        stac_api_certificate_arn: str,
        app_domain_hosted_zone_id: str,
        ecs_security_group_id: str,
        tags: Dict[str, str],
    ) -> None:
        super().__init__(scope, id)

        resource_prefix = f"{project_prefix}-{environment}"
        keycloak_issuer_url = os.getenv("KEYCLOAK_ISSUER_URL", "http://localhost:8080/realms/your-realm")
        
        stac_api_fqdn = f"{app_config.stac_api_subdomain}.{app_config.domain_name}"

        # 1. Create Network Load Balancer (NLB) for STAC ECS Service
        self.nlb = Nlb(
            self, "stac-nlb",
            name=f"{resource_prefix}-stac-nlb",
            internal=True,
            load_balancer_type="network",
            subnets=private_subnet_ids,
            enable_cross_zone_load_balancing=True,
            tags={**tags, "Name": f"{resource_prefix}-stac-nlb"},
        )

        self.stac_nlb_target_group = NlbTargetGroup(
            self, "stac-nlb-tg",
            name=f"{resource_prefix}-stac-nlb-tg",
            port=stac_service_config.container_port,
            protocol="TCP",
            vpc_id=vpc_id,
            target_type="ip", 
            health_check={
                "enabled": True, "protocol": "TCP",
                "port": str(stac_service_config.container_port),
                "interval": 30, "healthy_threshold": 2, "unhealthy_threshold": 2,
            },
            tags={**tags, "Name": f"{resource_prefix}-stac-nlb-tg"},
        )
        
        self.stac_nlb_listener = LbListener(
            self, "stac-nlb-listener",
            load_balancer_arn=self.nlb.arn,
            port=stac_service_config.container_port,
            protocol="TCP",
            default_action=[
                LbListenerDefaultAction(type="forward", target_group_arn=self.stac_nlb_target_group.arn)
            ],
            tags=tags,
        )
        
        self.stac_nlb_target_group_arn_output = TerraformOutput(
            self, "stac_nlb_target_group_arn",
            value=self.stac_nlb_target_group.arn,
            description="ARN of the NLB Target Group for STAC API",
        )

        # 2. Create VPC Link for API Gateway
        self.vpc_link = Apigatewayv2VpcLink(
            self, "stac-vpc-link",
            name=f"{resource_prefix}-stac-vpc-link",
            subnet_ids=private_subnet_ids,
            security_group_ids=[ecs_security_group_id],
            tags=tags,
        )

        # 3. Create API Gateway HTTP API
        self.http_api = Apigatewayv2Api(
            self, "stac-http-api",
            name=f"{resource_prefix}-stac-api",
            protocol_type="HTTP",
            description=f"API Gateway for {resource_prefix} STAC API",
            tags=tags,
        )

        # 4. Create JWT Authorizer for Keycloak
        self.jwt_authorizer = Apigatewayv2Authorizer(
            self, "stac-jwt-authorizer",
            api_id=self.http_api.id,
            name=f"{resource_prefix}-stac-jwt-authorizer",
            authorizer_type="JWT",
            identity_sources=["$request.header.Authorization"],
            jwt_configuration=Apigatewayv2AuthorizerJwtConfiguration(
                audience=app_config.api_gateway.stac_api_jwt_audience,
                issuer=keycloak_issuer_url,
            ),
        )

        # 5. Create Integration with the NLB via VPC Link
        self.nlb_integration = Apigatewayv2Integration(
            self, "stac-nlb-integration",
            api_id=self.http_api.id,
            integration_type="HTTP_PROXY",
            integration_uri=self.stac_nlb_listener.arn,
            integration_method="ANY",
            connection_type="VPC_LINK",
            connection_id=self.vpc_link.id,
            payload_format_version="1.0"
        )

        # 6. Define Routes for STAC API
        # Dictionary to track created routes and avoid duplicates
        created_routes = {}

        # Define the public routes (GET and OPTIONS)
        public_routes_map = {
            "GET /": "get-root",
            "GET /{proxy+}": "get-proxy",
            "OPTIONS /": "options-root",
            "OPTIONS /{proxy+}": "options-proxy",
        }

        # Create the public routes
        for route_key, route_id_suffix in public_routes_map.items():
            created_routes[route_key] = True
            Apigatewayv2Route(
                self, f"stac-public-route-{route_id_suffix}",
                api_id=self.http_api.id, 
                route_key=route_key,
                target=f"integrations/{self.nlb_integration.id}",
            )

        # Create secured routes with JWT auth
        secured_methods = ["POST", "PUT", "DELETE", "PATCH"]
        for method in secured_methods:
            # Base path routes
            route_key_base = f"{method} /"
            if route_key_base not in created_routes:
                created_routes[route_key_base] = True
                Apigatewayv2Route(
                    self, f"stac-secured-route-{method.lower()}-base",
                    api_id=self.http_api.id, 
                    route_key=route_key_base,
                    target=f"integrations/{self.nlb_integration.id}",
                    authorizer_id=self.jwt_authorizer.id, 
                    authorization_type="JWT",
                )
            
            # Proxy routes
            route_key_proxy = f"{method} /{{proxy+}}"
            if route_key_proxy not in created_routes:
                created_routes[route_key_proxy] = True
                Apigatewayv2Route(
                    self, f"stac-secured-route-{method.lower()}-proxy",
                    api_id=self.http_api.id, 
                    route_key=route_key_proxy,
                    target=f"integrations/{self.nlb_integration.id}",
                    authorizer_id=self.jwt_authorizer.id, 
                    authorization_type="JWT",
                )

        # 7. Create Custom Domain Name for API Gateway
        self.api_domain_name_resource = Apigatewayv2DomainName(
            self, "stac-api-domain-name",
            domain_name=stac_api_fqdn,
            domain_name_configuration=Apigatewayv2DomainNameDomainNameConfiguration(
                certificate_arn=stac_api_certificate_arn,
                endpoint_type="REGIONAL",
                security_policy="TLS_1_2"
            ),
            tags=tags,
        )

        # 8. Create Route53 Alias Record for the custom domain
        self.stac_api_dns_record = Route53Record(
            self, "stac-api-custom-domain-alias",
            zone_id=app_domain_hosted_zone_id,
            name=stac_api_fqdn,
            type="A",
            alias={
                "name": self.api_domain_name_resource.domain_name_configuration.target_domain_name,
                "zone_id": self.api_domain_name_resource.domain_name_configuration.hosted_zone_id,
                "evaluate_target_health": False,
            },
        )

        # 9. Create Default Stage
        self.stage = Apigatewayv2Stage(
            self, "stac-api-default-stage",
            api_id=self.http_api.id,
            name="$default",
            auto_deploy=True,
            tags=tags,
        )
        
        # 10. Create API Mapping
        self.api_mapping = Apigatewayv2ApiMapping(
            self, "stac-api-domain-mapping",
            api_id=self.http_api.id,
            domain_name=self.api_domain_name_resource.id,
            stage=self.stage.id,
        )

        self.stac_api_custom_domain_url_output = TerraformOutput(
            self, "stac_api_custom_domain_url",
            value=f"https://{stac_api_fqdn}",
            description="Custom Domain URL for the STAC API Gateway",
        )
        self.api_gateway_invoke_url_output = TerraformOutput(
            self, "stac_api_gateway_invoke_url_regional",
            value=self.http_api.api_endpoint,
            description="Regional Invoke URL for the STAC API Gateway",
        )