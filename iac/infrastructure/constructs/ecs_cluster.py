from typing import List
from constructs import Construct
from cdktf import TerraformOutput
from cdktf_cdktf_provider_aws.ecs_cluster import EcsCluster
from cdktf_cdktf_provider_aws.instance import Instance
from cdktf_cdktf_provider_aws.data_aws_ssm_parameter import DataAwsSsmParameter


class EcsClusterConstruct(Construct):
    """
    A construct for creating an ECS cluster and its EC2 capacity providers.

    This construct creates an Amazon ECS cluster and provisions EC2 instances to serve as container hosts.
    It handles the complete setup of the cluster infrastructure including:
    1. ECS cluster creation with container insights enabled
    2. EC2 instances using the latest ECS-optimized Amazon Linux 2 AMI
    3. Auto-registration of instances with the ECS cluster
    4. Instance metadata service v2 (IMDSv2) configuration
    5. EBS volume encryption and configuration
    6. Integration with CloudWatch for container insights

    The EC2 instances are configured with:
    - ECS container agent and configuration
    - Container metadata enabled
    - Root volume encryption
    - IMDSv2 requirement for enhanced security
    - Round-robin distribution across specified subnets
    - User data script for ECS cluster registration

    Attributes:
        cluster (EcsCluster): The ECS cluster resource
        instances (List[Instance]): List of EC2 instances serving as container hosts

    Parameters:
        scope (Construct): The scope in which this construct is defined
        id (str): The scoped construct ID
        project_prefix (str): Prefix for resource names (e.g., "project-name")
        environment (str): Environment name (e.g., "prod", "dev")
        instance_type (str): EC2 instance type (e.g., "t3.medium")
        instance_count (int): Number of EC2 instances to provision
        subnet_ids (List[str]): List of subnet IDs for instance placement
        security_group_id (str): Security group ID for the EC2 instances
        instance_profile_name (str): IAM instance profile name for EC2 instances
        tags (dict): Tags to apply to all resources

    Example:
        ```python
        cluster = EcsClusterConstruct(
            self,
            "ecs-cluster",
            project_prefix="myapp",
            environment="prod",
            instance_type="t3.medium",
            instance_count=2,
            subnet_ids=["subnet-1", "subnet-2"],
            security_group_id="sg-123",
            instance_profile_name="ecs-instance-profile",
            tags={"Environment": "production"}
        )
        ```

    Notes:
        - Uses the latest ECS-optimized AMI from SSM Parameter Store
        - Instances are distributed across subnets in a round-robin fashion
        - Root volumes are encrypted and sized to 30GB using gp3
        - Container insights are enabled on the cluster by default
        - Each instance automatically joins the cluster via user data script
        - Instance IDs are exported as TerraformOutputs for reference
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        project_prefix: str,
        environment: str,
        instance_type: str,
        instance_count: int,
        subnet_ids: List[str],
        security_group_id: str,
        instance_profile_name: str,
        tags: dict,
    ) -> None:
        super().__init__(scope, id)

        resource_prefix = f"{project_prefix}-{environment}"

        # Create ECS cluster
        self.cluster = EcsCluster(
            self,
            "cluster",
            name=f"{resource_prefix}-cluster",
            tags=tags,
            setting=[{"name": "containerInsights", "value": "enabled"}],
        )

        # Get the latest ECS-optimized AMI from SSM Parameter Store
        latest_ecs_ami = DataAwsSsmParameter(
            self,
            "ecs-ami",
            name="/aws/service/ecs/optimized-ami/amazon-linux-2/recommended/image_id",
        )

        # Create EC2 instances for ECS cluster
        self.instances = []
        for i in range(instance_count):
            user_data = f"""#!/bin/bash
echo "ECS_CLUSTER={self.cluster.name}" >> /etc/ecs/ecs.config
echo "ECS_ENABLE_CONTAINER_METADATA=true" >> /etc/ecs/ecs.config"""

            instance = Instance(
                self,
                f"ecs-instance-{i + 1}",
                ami=latest_ecs_ami.value,
                instance_type=instance_type,
                subnet_id=subnet_ids[i % len(subnet_ids)],  # Round-robin across subnets
                iam_instance_profile=instance_profile_name,
                vpc_security_group_ids=[security_group_id],
                user_data=user_data,
                metadata_options={
                    "http_endpoint": "enabled",
                    "http_tokens": "required",  # IMDSv2
                },
                root_block_device={
                    "volume_size": 30,
                    "volume_type": "gp3",
                    "encrypted": True,
                },
                tags={
                    **tags,
                    "Name": f"{resource_prefix}-ecs-instance-{i + 1}",
                },
            )
            self.instances.append(instance)

            # Add output for instance ID
            TerraformOutput(
                self,
                f"instance-id-{i + 1}",
                value=instance.id,
                description=f"EC2 Instance ID {i + 1}",
            )
