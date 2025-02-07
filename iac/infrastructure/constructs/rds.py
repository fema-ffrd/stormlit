from typing import List
from constructs import Construct
from cdktf_cdktf_provider_aws.db_instance import DbInstance
from cdktf_cdktf_provider_aws.db_subnet_group import DbSubnetGroup
from cdktf_cdktf_provider_aws.db_parameter_group import (
    DbParameterGroup,
    DbParameterGroupParameter,
)
from config import DatabaseConfig


class RdsConstruct(Construct):
    """
    A construct for creating and configuring an Amazon RDS PostgreSQL instance.

    This construct manages the creation of an RDS instance and its supporting resources:
    1. DB subnet group for network placement
    2. Parameter group for PostgreSQL configuration
    3. RDS instance with specified settings
    4. Backup and maintenance configurations
    5. Security and monitoring settings

    Database Configuration:
    - PostgreSQL 17.2 engine
    - Custom parameter group settings:
        * max_connections: 100
        * shared_buffers: 16MB
        * rds.force_ssl: disabled

    Infrastructure:
    - Placed in private subnets via subnet group
    - Security group controls access
    - Storage encryption enabled
    - Performance insights available
    - CloudWatch monitoring integration

    Backup and Recovery:
    - Configurable backup retention period
    - Optional final snapshot on deletion
    - Point-in-time recovery capability
    - Automated backups enabled

    Attributes:
        db_instance (DbInstance): The RDS instance resource

    Parameters:
        scope (Construct): The scope in which this construct is defined
        id (str): The scoped construct ID
        project_prefix (str): Prefix for resource names
        environment (str): Environment name (e.g., "prod", "dev")
        subnet_ids (List[str]): List of subnet IDs for DB subnet group
        security_group_id (str): Security group ID for RDS instance
        db_config (DatabaseConfig): Database configuration settings
        master_username (str): Master user username
        master_password (str): Master user password
        tags (dict): Tags to apply to all resources

    Example:
        ```python
        rds = RdsConstruct(
            self,
            "rds",
            project_prefix="myapp",
            environment="prod",
            subnet_ids=["subnet-1", "subnet-2"],
            security_group_id="sg-123",
            db_config=DatabaseConfig(
                instance_class="db.t4g.medium",
                allocated_storage=20,
                max_allocated_storage=100,
                deletion_protection=True,
                multi_az=True,
                backup_retention_period=7,
                publicly_accessible=False
            ),
            master_username="dbadmin",
            master_password=generated_password,
            tags={"Environment": "production"}
        )
        ```

    Notes:
        - Instance is configured for PostgreSQL workloads
        - Storage is encrypted by default
        - Parameter group changes require instance reboot
        - Auto minor version upgrades enabled
        - Tags are copied to snapshots
        - Port 5432 is used for PostgreSQL
        - Max connections limited to 100
        - Performance monitoring interval configurable
        - Multi-AZ deployment optional
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        project_prefix: str,
        environment: str,
        subnet_ids: List[str],
        security_group_id: str,
        db_config: DatabaseConfig,
        master_username: str,
        master_password: str,
        tags: dict,
    ) -> None:
        super().__init__(scope, id)

        resource_prefix = f"{project_prefix}-{environment}"

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
            family="postgres17",
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
                DbParameterGroupParameter(
                    name="rds.force_ssl",
                    value="0",
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
            engine_version="17.2",
            instance_class=db_config.instance_class,
            allocated_storage=db_config.allocated_storage,
            max_allocated_storage=db_config.max_allocated_storage,
            db_name=f"{project_prefix}_{environment}_db",
            username=master_username,
            password=master_password,
            multi_az=db_config.multi_az,
            db_subnet_group_name=db_subnet_group.name,
            vpc_security_group_ids=[security_group_id],
            parameter_group_name=db_parameter_group.name,
            backup_retention_period=db_config.backup_retention_period,
            deletion_protection=db_config.deletion_protection,
            skip_final_snapshot=db_config.skip_final_snapshot,
            final_snapshot_identifier=f"{resource_prefix}-final-snapshot",
            publicly_accessible=db_config.publicly_accessible,
            apply_immediately=db_config.apply_immediately,
            copy_tags_to_snapshot=True,
            auto_minor_version_upgrade=True,
            monitoring_interval=db_config.monitoring_interval,
            performance_insights_enabled=db_config.performance_insights_enabled,
            storage_encrypted=True,
            port=5432,
            tags=tags,
        )
