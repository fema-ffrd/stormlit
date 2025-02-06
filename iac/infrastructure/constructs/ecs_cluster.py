from typing import List
from constructs import Construct
from cdktf import TerraformOutput
from cdktf_cdktf_provider_aws.ecs_cluster import EcsCluster
from cdktf_cdktf_provider_aws.instance import Instance
from cdktf_cdktf_provider_aws.data_aws_ssm_parameter import DataAwsSsmParameter


class EcsClusterConstruct(Construct):
    """
    A Construct for creating an ECS cluster along with EC2 instances to serve as its capacity providers.

    This construct manages the setup of an ECS cluster in AWS, along with EC2 instances configured as
    capacity providers. It ensures the necessary infrastructure is provisioned to run ECS tasks efficiently,
    leveraging Amazon ECS-optimized AMIs, instance profiles, and network configurations.

    Attributes:
        cluster (EcsCluster): The ECS cluster created by this construct.
        instances (List[Instance]): List of EC2 instances serving as capacity providers for the ECS cluster.

    Parameters:
        scope (Construct): The scope in which this construct is defined.
        id (str): The unique identifier of the construct.
        project_prefix (str): A prefix for project-related resource names to ensure uniqueness.
        environment (str): The environment name (e.g., `development`, `production`) to differentiate resources.
        instance_type (str): The EC2 instance type used for capacity provisioning.
        instance_count (int): The number of EC2 instances to provision for the ECS cluster.
        subnet_ids (List[str]): A list of subnet IDs where the ECS instances will be deployed.
        security_group_id (str): The security group ID to apply to the ECS instances.
        instance_profile_name (str): The IAM instance profile name to attach to the ECS instances.
        tags (dict): A dictionary of tags to apply to all resources created by this construct.

    Methods:
        __init__(self, scope, id, ...): Initializes the ECS cluster and EC2 instances.
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
