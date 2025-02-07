#!/usr/bin/env python
import os
from cdktf import App, Token, Fn
from infrastructure.stacks.network_stack import NetworkStack
from infrastructure.stacks.database_stack import DatabaseStack
from infrastructure.stacks.application_stack import ApplicationStack

from config import get_config


def main():
    """
    Main entry point for deploying the complete infrastructure using CDKTF.

    This function orchestrates the deployment of a multi-tier application infrastructure including:
    1. Network infrastructure (VPC, subnets, security groups)
    2. Database infrastructure (RDS PostgreSQL, Secrets)
    3. Application infrastructure (ECS, ALB, STAC API, Streamlit)

    Stack Dependencies:
    - Network Stack
        └── Database Stack
            └── Application Stack

    Components:
    - Network Stack:
        * VPC and subnets
        * Security groups
        * Routing configuration

    - Database Stack:
        * RDS PostgreSQL instance
        * Database credentials
        * PgSTAC user setup

    - Application Stack:
        * ECS cluster and services
        * Application Load Balancer
        * STAC API and Streamlit services

    Environment:
        - Determined by ENVIRONMENT environment variable
        - Defaults to "dev" if not specified
        - Supported values: "dev", "prod"
        - Configuration loaded dynamically based on environment

    Configuration:
        - Project prefix for resource naming
        - Environment-specific settings
        - Network CIDR and AZ configuration
        - Database instance settings
        - ECS service configurations

    Example Usage:
        ```bash
        # Deploy to development
        ENVIRONMENT=dev TF_VAR_stormlit_tag=dev cdktf deploy stormlit-dev-network stormlit-dev-database stormlit-dev-application

        # Deploy to production
        ENVIRONMENT=prod TF_VAR_stormlit_tag=latest cdktf deploy stormlit-prod-network stormlit-prod-database stormlit-prod-application
        ```

    Notes:
        - Maintains proper stack dependencies
        - Uses token passing for cross-stack references
        - Supports multiple environments
        - Infrastructure as Code using CDKTF
        - Follows AWS best practices
        - All resources properly tagged
    """

    # Initialize the CDKTF app
    app = App()

    # Get environment from ENV var, default to development
    environment = os.getenv("ENVIRONMENT", "dev")
    config = get_config(environment)

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
        rds_host=Token.as_string(
            Fn.element(Fn.split(":", database_stack.rds.db_instance.endpoint), 0)
        ),
        pgstac_read_secret_arn=Token.as_string(
            database_stack.secrets.pgstac_read_secret.arn
        ),
    )

    # # Add dependency between stacks
    database_stack.add_dependency(network_stack)
    application_stack.add_dependency(database_stack)

    app.synth()


if __name__ == "__main__":
    main()
