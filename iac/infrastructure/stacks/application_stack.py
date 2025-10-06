from typing import List
from constructs import Construct
from cdktf import TerraformOutput, TerraformVariable, Token
from config import EnvironmentConfig, ServiceRoles
from .base_stack import BaseStack
from ..constructs.ecs_iam import EcsIamConstruct
from ..constructs.alb import AlbConstruct
from ..constructs.ecs_cluster import EcsClusterConstruct
from ..constructs.ecs_services import EcsServicesConstruct
from ..constructs.api_gateway import ApiGatewayConstruct
from ..constructs.cloud_watch import CloudWatchConstruct


class ApplicationStack(BaseStack):
    """
    A stack that deploys the complete application infrastructure on AWS ECS.
    Includes ALB for Stormlit (OIDC auth) and API Gateway for STAC API (JWT auth with custom domain).
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
        ecs_security_group_id: str,
        rds_host: str,
        pgstac_admin_secret_arn: str,
    ) -> None:
        super().__init__(scope, id, config)

        stormlit_tag_var = TerraformVariable(
            self,
            "stormlit_tag",
            type="string",
            description="Version tag for the stormlit image",
            default="latest",
        )
        config.ecs.stormlit_config.image_tag = (
            config.ecs.stormlit_config.image_tag or stormlit_tag_var.string_value
        )

        cloudwatch_logs = CloudWatchConstruct(
            self,
            "cloudwatch-logs",
            project_prefix=config.project_prefix,
            environment=config.environment,
            tags=config.tags,
        )

        self.iam = EcsIamConstruct(
            self,
            "ecs-iam",
            project_prefix=config.project_prefix,
            environment=config.environment,
            secret_arns=[pgstac_admin_secret_arn],
            services={
                "stormlit": {
                    "task_role_statements": [
                        {
                            "Effect": "Allow",
                            "Action": ["s3:GetObject", "s3:ListBucket"],
                            "Resource": "*",
                        }
                    ],
                    "execution_role_statements": [],
                },
                "stac-api": {
                    "task_role_statements": [],
                    "execution_role_statements": [],
                    "secret_arns": [pgstac_admin_secret_arn],
                },
                "flood-data-plotter": {
                    "task_role_statements": [],
                    "execution_role_statements": [],
                },
            },
            tags=config.tags,
        )

        self.ecs_cluster = EcsClusterConstruct(
            self,
            "ecs-cluster",
            project_prefix=config.project_prefix,
            environment=config.environment,
            instance_type=config.ecs.instance_type,
            instance_count=config.ecs.instance_count,
            subnet_ids=private_subnet_ids,
            security_group_id=ecs_security_group_id,
            instance_profile_name=Token.as_string(self.iam.instance_profile.name),
            tags=config.tags,
        )

        self.alb = AlbConstruct(
            self,
            "alb",
            project_prefix=config.project_prefix,
            environment=config.environment,
            app_config=config.application,
            vpc_id=vpc_id,
            public_subnet_ids=public_subnet_ids,
            security_group_id=alb_security_group_id,
            tags=config.tags,
        )

        stac_api_cert_arn_val = Token.as_string(
            self.alb.stac_api_certificate_arn_for_apigw_output.value
        )
        app_domain_hz_id_val = Token.as_string(
            self.alb.app_domain_hosted_zone_id_output.value
        )

        self.api_gateway = ApiGatewayConstruct(
            self,
            "stac-api-gateway",
            project_prefix=config.project_prefix,
            environment=config.environment,
            app_config=config.application,
            vpc_id=vpc_id,
            private_subnet_ids=private_subnet_ids,
            stac_service_config=config.ecs.stac_api_config,
            stac_api_certificate_arn=stac_api_cert_arn_val,
            app_domain_hosted_zone_id=app_domain_hz_id_val,
            ecs_security_group_id=ecs_security_group_id,
            tags=config.tags,
        )

        service_roles_map = {
            "stormlit": ServiceRoles(
                execution_role_arn=Token.as_string(
                    self.iam.service_execution_roles["stormlit"].arn
                ),
                task_role_arn=Token.as_string(
                    self.iam.service_task_roles["stormlit"].arn
                ),
            ),
            "stac-api": ServiceRoles(
                execution_role_arn=Token.as_string(
                    self.iam.service_execution_roles["stac-api"].arn
                ),
                task_role_arn=Token.as_string(
                    self.iam.service_task_roles["stac-api"].arn
                ),
            ),
            "flood-data-plotter": ServiceRoles(
                execution_role_arn=Token.as_string(
                    self.iam.service_execution_roles["flood-data-plotter"].arn
                ),
                task_role_arn=Token.as_string(
                    self.iam.service_task_roles["flood-data-plotter"].arn
                ),
            ),
        }

        ecs_services_construct = EcsServicesConstruct(
            self,
            "ecs-services",
            app_config=config.application,
            region=config.region,
            project_prefix=config.project_prefix,
            environment=config.environment,
            cluster_id=Token.as_string(self.ecs_cluster.cluster.id),
            cluster_name=Token.as_string(self.ecs_cluster.cluster.name),
            service_roles=service_roles_map,
            private_subnet_ids=private_subnet_ids,
            security_group_id=ecs_security_group_id,
            stormlit_alb_target_group_arn=Token.as_string(
                self.alb.app_target_group.arn
            ),
            stac_api_nlb_target_group_arn=Token.as_string(
                self.api_gateway.stac_nlb_target_group.arn
            ),
            ecs_config=config.ecs,
            rds_host=rds_host,
            pgstac_admin_secret_arn=pgstac_admin_secret_arn,
            tags=config.tags,
            vpc_id=vpc_id,
        )

        ecs_services_construct.node.add_dependency(self.alb)
        ecs_services_construct.node.add_dependency(self.api_gateway)
        ecs_services_construct.node.add_dependency(self.ecs_cluster)
        ecs_services_construct.node.add_dependency(self.iam)
        ecs_services_construct.node.add_dependency(cloudwatch_logs)

        TerraformOutput(
            self,
            "stormlit_alb_dns_name",
            value=self.alb.alb.dns_name,
            description="Application Load Balancer DNS Name (for Stormlit)",
        )
        TerraformOutput(
            self,
            "stac_api_custom_domain_url",
            value=f"https://{config.application.stac_api_subdomain}.{config.application.domain_name}",
            description="STAC API Gateway Custom Domain URL",
        )
        TerraformOutput(
            self,
            "cluster_name",
            value=self.ecs_cluster.cluster.name,
            description="ECS Cluster Name",
        )
