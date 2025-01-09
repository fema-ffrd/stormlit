#!/usr/bin/env python
import os
from cdktf import App, Token
from infrastructure.stacks.database_stack import DatabaseStack
from infrastructure.stacks.application_stack import ApplicationStack
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

    # Create the database stack
    database_stack = DatabaseStack(
        app,
        f"{config.project_prefix}-{environment}-database",
        config,
    )

    # Create the application stack with references to database resources
    application_stack = ApplicationStack(
        app,
        f"{config.project_prefix}-{environment}-application",
        config,
        vpc_id=Token.as_string(database_stack.networking.vpc.id),
        public_subnet_ids=[
            subnet.id for subnet in database_stack.networking.public_subnets
        ],
        private_subnet_ids=[
            subnet.id for subnet in database_stack.networking.private_subnets
        ],
        alb_security_group_id=Token.as_string(
            database_stack.networking.alb_security_group.id
        ),
        rds_endpoint=Token.as_string(database_stack.rds.db_instance.endpoint),
        database_secret_arn=Token.as_string(database_stack.secrets.database_secret.arn),
        keycloak_secret_arn=Token.as_string(database_stack.secrets.keycloak_secret.arn),
        streamlit_secret_arn=Token.as_string(database_stack.secrets.streamlit_secret.arn),
    )

    # Add dependency between stacks
    application_stack.add_dependency(database_stack)

    app.synth()


if __name__ == "__main__":
    main()
