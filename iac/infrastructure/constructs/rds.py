from typing import List
from constructs import Construct
from cdktf_cdktf_provider_aws.db_instance import DbInstance
from cdktf_cdktf_provider_aws.db_subnet_group import DbSubnetGroup
from cdktf_cdktf_provider_aws.db_parameter_group import (
    DbParameterGroup,
    DbParameterGroupParameter,
)
from cdktf_cdktf_provider_aws.security_group import SecurityGroup
from cdktf_cdktf_provider_aws.subnet import Subnet


class RdsConstruct(Construct):
    """
    A Construct to create an AWS RDS instance with associated configuration.

    This construct manages the creation of RDS instances with various configurations, including database
    subnet groups, parameter groups, and security groups. It handles settings such as instance class,
    allocated storage, multi-AZ deployment, backup retention periods, and deletion protection.
    Security group associations ensure proper network access controls.

    Attributes:
        db_instance (DbInstance): The RDS instance created by this construct.

    Parameters:
        scope (Construct): The scope in which this construct is defined.
        id (str): A unique identifier for the construct.
        project_prefix (str): A prefix for naming resources to help differentiate between environments.
        environment (str): The environment name (e.g., `production`, `development`) for tagging purposes.
        private_subnets (List[Subnet]): A list of private subnets to associate with the RDS instance.
        public_subnets (List[Subnet]): A list of public subnets to associate with the RDS instance.
        security_group (SecurityGroup): The security group to associate with the RDS instance.
        instance_class (str): The instance class/type for the RDS instance (e.g., `db.t2.micro`).
        allocated_storage (int): The amount of allocated storage for the RDS instance (in GB).
        max_allocated_storage (int): The maximum storage allocated for the RDS instance (in GB).
        multi_az (bool): Whether to deploy the RDS instance across multiple Availability Zones.
        deletion_protection (bool): Whether to enable deletion protection for the RDS instance.
        backup_retention_period (int): The number of days to retain backups.
        tags (dict): A dictionary of tags to apply to the RDS resources.

    Methods:
        __init__(self, scope, id, ...): Initializes the RDS setup for the AWS environment.

    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        project_prefix: str,
        environment: str,
        private_subnets: List[Subnet],
        public_subnets: List[Subnet],
        security_group: SecurityGroup,
        instance_class: str,
        allocated_storage: int,
        max_allocated_storage: int,
        multi_az: bool,
        deletion_protection: bool,
        backup_retention_period: int,
        master_username: str,
        master_password: str,
        tags: dict,
    ) -> None:
        super().__init__(scope, id)

        resource_prefix = f"{project_prefix}-{environment}"

        # Create DB subnet group with both public subnets for development and private subnets for production
        subnet_ids = (
            [subnet.id for subnet in public_subnets]
            if environment == "development"
            else [subnet.id for subnet in private_subnets]
        )
    
        db_subnet_group = DbSubnetGroup(
            self,
            "db-subnet-group",
            name=f"{resource_prefix}-db-subnet",
            subnet_ids=subnet_ids,
            description=f"Subnet group for {resource_prefix} RDS instances",
            tags={**tags, "Name": f"{resource_prefix}-db-subnet"},
        )

        # Create DB parameter group with explicit parameter configuration
        db_parameter_group = DbParameterGroup(
            self,
            "db-parameter-group",
            name=f"{resource_prefix}-db-params",
            family="postgres16",
            parameter=[
                DbParameterGroupParameter(
                    name="max_connections",
                    value="100",
                    apply_method="pending-reboot",
                ),
                DbParameterGroupParameter(
                    name="shared_buffers",
                    value="16384",  # 16MB in KB
                    apply_method="pending-reboot",
                ),
            ],
            tags={**tags, "Name": f"{resource_prefix}-db-params"},
        )

        # Create RDS instance
        self.db_instance = DbInstance(
            self,
            "db-instance",
            identifier=f"{resource_prefix}-postgres",
            engine="postgres",
            engine_version="16.6",
            instance_class=instance_class,
            allocated_storage=allocated_storage,
            max_allocated_storage=max_allocated_storage,
            db_name=f"{project_prefix}_{environment}_db",
            username=master_username,
            password=master_password,
            multi_az=multi_az,
            db_subnet_group_name=db_subnet_group.name,
            vpc_security_group_ids=[security_group.id],
            parameter_group_name=db_parameter_group.name,
            backup_retention_period=backup_retention_period,
            deletion_protection=deletion_protection,
            skip_final_snapshot=True if environment == "development" else False,
            final_snapshot_identifier=f"{resource_prefix}-final-snapshot",
            publicly_accessible=True if environment == "development" else False,
            apply_immediately=True if environment == "development" else False,
            copy_tags_to_snapshot=True,
            auto_minor_version_upgrade=True,
            monitoring_interval=60 if environment == "production" else 0,
            performance_insights_enabled=environment == "production",
            storage_encrypted=True,
            port=5432,
            tags=tags,
        )
