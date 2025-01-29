import json
from typing import List
from constructs import Construct
from cdktf import TerraformOutput
from cdktf_cdktf_provider_aws.iam_role import IamRole
from cdktf_cdktf_provider_aws.iam_role_policy_attachment import IamRolePolicyAttachment
from cdktf_cdktf_provider_aws.iam_role_policy import IamRolePolicy
from cdktf_cdktf_provider_aws.iam_instance_profile import IamInstanceProfile


class EcsIamConstruct(Construct):
    """
    A Construct to create IAM resources for an ECS setup, including instance roles, task roles, and execution roles.

    This construct manages the creation of IAM roles and instance profiles necessary for ECS EC2 instances,
    ECS task execution, and ECS tasks. It ensures the appropriate policies are attached to roles for accessing ECS
    services, AWS APIs, and other required resources.

    Attributes:
        instance_role (IamRole): The IAM role assigned to ECS EC2 instances.
        instance_profile (IamInstanceProfile): The IAM instance profile associated with ECS EC2 instances.
        execution_role (IamRole): The IAM role assigned to ECS task execution.
        task_role (IamRole): The IAM role assigned to ECS tasks.

    Parameters:
        scope (Construct): The scope in which this construct is defined.
        id (str): A unique identifier for the construct.
        project_prefix (str): A prefix for naming resources, helping to differentiate between environments.
        environment (str): The environment name (e.g., `development`, `production`) to ensure resources are
            appropriately tagged.
        tags (dict): A dictionary of tags to apply to all IAM resources created by this construct.

    Methods:
        __init__(self, scope, id, ...): Initializes the IAM roles and instance profile for ECS instances,
            task execution, and tasks.
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        project_prefix: str,
        environment: str,
        secret_arns: List[str],
        tags: dict,
    ) -> None:
        super().__init__(scope, id)

        resource_prefix = f"{project_prefix}-{environment}"

        # Create ECS instance role
        self.instance_role = IamRole(
            self,
            "instance-role",
            name=f"{resource_prefix}-ecs-instance-role",
            assume_role_policy="""{
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Action": "sts:AssumeRole",
                        "Principal": {
                            "Service": "ec2.amazonaws.com"
                        },
                        "Effect": "Allow"
                    }
                ]
            }""",
            tags=tags,
        )

        # Attach ECS instance role policy
        IamRolePolicyAttachment(
            self,
            "instance-policy",
            role=self.instance_role.name,
            policy_arn="arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role",
        )

        # Add SSM policy for troubleshooting
        IamRolePolicyAttachment(
            self,
            "instance-policy-2",
            role=self.instance_role.name,
            policy_arn="arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
        )

        # Create instance profile
        self.instance_profile = IamInstanceProfile(
            self,
            "instance-profile",
            name=f"{resource_prefix}-ecs-instance-profile",
            role=self.instance_role.name,
        )

        # Create ECS task execution role
        execution_role_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "logs:CreateLogGroup",
                        "logs:CreateLogStream",
                        "logs:PutLogEvents",
                        "logs:DescribeLogGroups",
                        "logs:DescribeLogStreams",
                    ],
                    "Resource": "*",
                },
                {
                    "Effect": "Allow",
                    "Action": [
                        "secretsmanager:GetSecretValue",
                        "secretsmanager:DescribeSecret",
                    ],
                    "Resource": secret_arns,
                },
                {
                    "Effect": "Allow",
                    "Action": [
                        "ecr:GetAuthorizationToken",
                        "ecr:BatchCheckLayerAvailability",
                        "ecr:GetDownloadUrlForLayer",
                        "ecr:BatchGetImage",
                    ],
                    "Resource": "*",
                },
                {
                    "Effect": "Allow",
                    "Action": [
                        "s3:GetObject",
                        "s3:ListBucket",
                    ],
                    "Resource": "*",
                },
            ],
        }

        self.execution_role = IamRole(
            self,
            "execution-role",
            name=f"{resource_prefix}-ecs-execution-role",
            assume_role_policy="""{
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Action": "sts:AssumeRole",
                        "Principal": {
                            "Service": "ecs-tasks.amazonaws.com"
                        },
                        "Effect": "Allow"
                    }
                ]
            }""",
            inline_policy=[
                {
                    "name": "ecs-execution-policy",
                    "policy": json.dumps(execution_role_policy),
                }
            ],
            tags=tags,
        )

        # Attach ECS task execution role policy
        IamRolePolicyAttachment(
            self,
            "execution-policy",
            role=self.execution_role.name,
            policy_arn="arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy",
        )

        # Add CloudWatch Logs policy for execution role
        cloudwatch_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "logs:CreateLogGroup",
                        "logs:CreateLogStream",
                        "logs:PutLogEvents",
                        "logs:DescribeLogGroups",
                        "logs:DescribeLogStreams",
                    ],
                    "Resource": "*",
                }
            ],
        }

        IamRolePolicy(
            self,
            "execution-cloudwatch-policy",
            name=f"{resource_prefix}-ecs-cloudwatch-policy",
            role=self.execution_role.name,
            policy=json.dumps(cloudwatch_policy),
        )

        # Create ECS task role
        self.task_role = IamRole(
            self,
            "task-role",
            name=f"{resource_prefix}-ecs-task-role",
            assume_role_policy="""{
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Action": "sts:AssumeRole",
                        "Principal": {
                            "Service": "ecs-tasks.amazonaws.com"
                        },
                        "Effect": "Allow"
                    },
                    {
                        "Effect": "Allow",
                        "Action": [
                            "s3:GetObject",
                            "s3:ListBucket",
                        ],
                        "Resource": "*",
                    },
                ]
            }""",
            tags=tags,
        )

        # output the ARNs of the roles
        TerraformOutput(
            self,
            "instance-role-arn",
            value=self.instance_role.arn,
            description="Instance Role ARN",
        )

        TerraformOutput(
            self,
            "execution-role-arn",
            value=self.execution_role.arn,
            description="Execution Role ARN",
        )

        TerraformOutput(
            self,
            "task-role-arn",
            value=self.task_role.arn,
            description="Task Role ARN",
        )
