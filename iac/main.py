#!/usr/bin/env python
import os
from cdktf import App, Token
from infrastructure.stacks.network_stack import NetworkStack
from infrastructure.stacks.database_stack import DatabaseStack
from infrastructure.stacks.application_stack import ApplicationStack
from infrastructure.stacks.postgres_init_stack import PostgresInitStack
from infrastructure.stacks.application_stack_dev import ApplicationStackDev
from config import get_config


def main():
    """
    The main entry point for the CDKTF deployment script.

    This script initializes the CDKTF application, retrieves the configuration for the specified environment, and
    creates the necessary infrastructure stacks (DatabaseStack and ApplicationStack) using the provided configuration.
    It also manages the relationships between the stacks, ensuring correct dependencies are established.

    Steps:
        1. Retrieve the deployment environment from the `ENVIRONMENT` environment variable, defaulting to "development".
        2. Fetch the configuration settings for the specified environment using `get_config`.
        3. Initialize the CDKTF application.
        4. Create the `DatabaseStack`, which provisions networking, VPC, and RDS resources.
        5. Create the `ApplicationStack`, which builds application-specific resources, using the outputs
            from the DatabaseStack.
        6. Establish the dependency between the ApplicationStack and DatabaseStack.
        7. Synthesize the application, generating the Terraform configurations.

    Raises:
        ValueError: If the specified environment is not recognized by `get_config`.

    """
    # Get environment from ENV var, default to development
    environment = os.getenv("ENVIRONMENT", "development")
    config = get_config(environment)

    # Initialize the CDKTF app
    app = App()

    network_stack = NetworkStack(
        app,
        f"{config.project_prefix}-{environment}-network",
        config,
    )

    # Create the database stack
    database_stack = DatabaseStack(
        app,
        f"{config.project_prefix}-{environment}-database",
        config,
        private_subnets=[
            subnet.id for subnet in network_stack.networking.private_subnets
        ],
        public_subnets=[
            subnet.id for subnet in network_stack.networking.public_subnets
        ],
        rds_security_group=Token.as_string(
            network_stack.networking.rds_security_group.id
        ),
    )

    postgres_init_stack = PostgresInitStack(
        app,
        f"{config.project_prefix}-{environment}-postgres-init",
        config,
        host=Token.as_string(
            f'${{split(":", {database_stack.rds.db_instance.endpoint})[0]}}'
        ),
        port=5432,
        db_admin_password=database_stack.random_passwords.database_password.result,
        keycloak_password=database_stack.random_passwords.keycloak_db_password.result,
        pgstac_password=database_stack.random_passwords.pgstac_db_password.result,
    )

    # Create the application stack with references to database resources
    application_stack = ApplicationStack(
        app,
        f"{config.project_prefix}-{environment}-application",
        config,
        vpc_id=Token.as_string(network_stack.networking.vpc.id),
        public_subnet_ids=[
            subnet.id for subnet in network_stack.networking.public_subnets
        ],
        private_subnet_ids=[
            subnet.id for subnet in network_stack.networking.private_subnets
        ],
        alb_security_group_id=Token.as_string(
            network_stack.networking.alb_security_group.id
        ),
        ecs_security_group_id=Token.as_string(
            network_stack.networking.ecs_security_group.id
        ),
        rds_endpoint=Token.as_string(database_stack.rds.db_instance.endpoint),
        database_secret_arn=Token.as_string(database_stack.secrets.database_secret.arn),
        keycloak_secret_arn=Token.as_string(database_stack.secrets.keycloak_secret.arn),
        keycloak_db_secret_arn=Token.as_string(
            database_stack.secrets.keycloak_db_secret.arn
        ),
        pgstac_db_secret_arn=Token.as_string(
            database_stack.secrets.pgstac_db_secret.arn
        ),
        streamlit_repository_url=config.application.stormlit_repo_url,
    )

    # Add dependency between stacks
    database_stack.add_dependency(network_stack)
    postgres_init_stack.add_dependency(database_stack)
    application_stack.add_dependency(database_stack)

    # Deploy streamlit dev container
    # This is specific to the arc pts dev environment
    # it deploys a streamlit container alongside the production deployments for testing and development purposes
    if environment == "development":
        ApplicationStackDev(
            app,
            f"{config.project_prefix}-{environment}-application-dev",
            config,
            vpc_id=Token.as_string(network_stack.networking.vpc.id),
            private_subnet_ids=[
                subnet.id for subnet in network_stack.networking.private_subnets
            ],
            security_group_id=Token.as_string(
                network_stack.networking.ecs_security_group.id
            ),
            alb_dns_name=Token.as_string(application_stack.alb.alb.dns_name),
            execution_role_arn=Token.as_string(
                application_stack.iam.execution_role.arn
            ),
            task_role_arn=Token.as_string(application_stack.iam.task_role.arn),
            cluster_id=Token.as_string(application_stack.ecs_cluster.cluster.id),
            streamlit_repository_url=config.application.stormlit_repo_url,
            https_listener_arn=Token.as_string(application_stack.alb.https_listener.arn),
        )

    app.synth()


if __name__ == "__main__":
    main()
