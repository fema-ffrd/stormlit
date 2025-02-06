#!/usr/bin/env python
import os
from cdktf import App, Token
from infrastructure.stacks.network_stack import NetworkStack
from infrastructure.stacks.database_stack import DatabaseStack

# from infrastructure.stacks.application_stack import ApplicationStack
# from infrastructure.stacks.postgres_init_stack import PostgresInitStack
# from infrastructure.stacks.application_stack_dev import ApplicationStackDev
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
    # Initialize the CDKTF app
    app = App()

    # Get environment from ENV var, default to development
    environment = os.getenv("ENVIRONMENT", "dev")
    config = get_config(environment, app)

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
        subnet_ids=[subnet.id for subnet in network_stack.networking.private_subnets],
        rds_security_group_id=Token.as_string(
            network_stack.networking.rds_security_group.id
        ),
    )
    #
    # # Create the application stack with references to database resources
    # application_stack = ApplicationStack(
    #     app,
    #     f"{config.project_prefix}-{environment}-application",
    #     config,
    #     vpc_id=Token.as_string(network_stack.networking.vpc.id),
    #     public_subnet_ids=[
    #         subnet.id for subnet in network_stack.networking.public_subnets
    #     ],
    #     private_subnet_ids=[
    #         subnet.id for subnet in network_stack.networking.private_subnets
    #     ],
    #     alb_security_group_id=Token.as_string(
    #         network_stack.networking.alb_security_group.id
    #     ),
    #     ecs_security_group_id=Token.as_string(
    #         network_stack.networking.ecs_security_group.id
    #     ),
    #     rds_endpoint=Token.as_string(database_stack.rds.db_instance.endpoint),
    #     database_secret_arn=Token.as_string(database_stack.secrets.database_secret.arn),
    #     keycloak_secret_arn=Token.as_string(database_stack.secrets.keycloak_secret.arn),
    #     keycloak_db_secret_arn=Token.as_string(
    #         database_stack.secrets.keycloak_db_secret.arn
    #     ),
    #     pgstac_db_secret_arn=Token.as_string(
    #         database_stack.secrets.pgstac_db_secret.arn
    #     ),
    #     streamlit_repository_url=config.application.stormlit_repo_url,
    # )
    #
    # # Add dependency between stacks
    # database_stack.add_dependency(network_stack)
    # application_stack.add_dependency(database_stack)

    app.synth()


if __name__ == "__main__":
    main()
