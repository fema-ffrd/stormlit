import json
from typing import List, Optional, Dict, Union
from constructs import Construct
from cdktf import TerraformOutput
from cdktf_cdktf_provider_aws.iam_role import IamRole
from cdktf_cdktf_provider_aws.iam_role_policy_attachment import IamRolePolicyAttachment
from cdktf_cdktf_provider_aws.iam_role_policy import IamRolePolicy
from cdktf_cdktf_provider_aws.iam_instance_profile import IamInstanceProfile


class EcsIamConstruct(Construct):
    """
    A Construct to create IAM resources for an ECS setup with support for multiple services.
    Each service can have its own execution and task roles with specific permissions.
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
        services: Dict[str, Dict[str, Union[List[dict], List[str]]]] = None,
    ) -> None:
        """
        Initialize the ECS IAM construct.

        Args:
            scope: The scope in which this construct is defined
            id: The scoped construct ID
            project_prefix: Prefix for resource names
            environment: Environment name (e.g., prod, dev)
            secret_arns: List of secret ARNs that ECS tasks need access to
            tags: Tags to apply to all resources
            services: Dictionary of service configurations in the format:
                {
                    "service_name": {
                        "task_role_statements": [{"Effect": "Allow", ...}],
                        "execution_role_statements": [{"Effect": "Allow", ...}],
                        "secret_arns": ["arn:aws:secretsmanager:..."]  # Optional secrets for this service
                    }
                }
        """
        super().__init__(scope, id)

        self.project_prefix = project_prefix
        self.environment = environment
        self.secret_arns = secret_arns
        self.tags = tags
        self.resource_prefix = f"{project_prefix}-{environment}"
        self.services = services or {}

        # Store roles for each service
        self.service_execution_roles: Dict[str, IamRole] = {}
        self.service_task_roles: Dict[str, IamRole] = {}

        # Create common instance role and profile
        self._create_instance_role_and_profile()

        # Create roles for each service
        for service_name, service_config in self.services.items():
            self._create_service_roles(
                service_name,
                service_config.get("task_role_statements", []),
                service_config.get("execution_role_statements", []),
                service_config.get("secret_arns", self.secret_arns),
            )

        # Output all role ARNs
        self._create_role_outputs()

    def _create_instance_role_and_profile(self) -> None:
        """Creates the common ECS instance role and profile."""
        self.instance_role = IamRole(
            self,
            "instance-role",
            name=f"{self.resource_prefix}-ecs-instance-role",
            assume_role_policy=self._get_assume_role_policy("ec2.amazonaws.com"),
            tags=self.tags,
        )

        # Attach policies to instance role
        for idx, policy_arn in enumerate(
            [
                "arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role",
                "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
            ]
        ):
            IamRolePolicyAttachment(
                self,
                f"instance-policy-{idx + 1}",
                role=self.instance_role.name,
                policy_arn=policy_arn,
            )

        self.instance_profile = IamInstanceProfile(
            self,
            "instance-profile",
            name=f"{self.resource_prefix}-ecs-instance-profile",
            role=self.instance_role.name,
        )

    def _create_service_roles(
        self,
        service_name: str,
        task_role_statements: List[dict],
        execution_role_statements: List[dict],
        service_secret_arns: Optional[List[str]] = None,
    ) -> None:
        """
        Creates execution and task roles for a specific service.

        Args:
            service_name: Name of the service
            task_role_statements: List of IAM policy statements for the task role
            execution_role_statements: List of IAM policy statements for the execution role
        """
        # Create execution role
        execution_role = self._create_execution_role(
            service_name, execution_role_statements, service_secret_arns
        )
        self.service_execution_roles[service_name] = execution_role

        # Create task role
        task_role = self._create_task_role(service_name, task_role_statements)
        self.service_task_roles[service_name] = task_role

    def _create_execution_role(
        self,
        service_name: str,
        additional_statements: List[dict],
        service_secret_arns: Optional[List[str]] = None,
    ) -> IamRole:
        """Creates an execution role for a specific service."""
        # Base execution role policy with required permissions
        base_statements = [
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
                "Resource": service_secret_arns or self.secret_arns,
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
        ]

        # Combine base statements with additional statements
        execution_role_policy = {
            "Version": "2012-10-17",
            "Statement": base_statements + additional_statements,
        }

        execution_role = IamRole(
            self,
            f"{service_name}-execution-role",
            name=f"{self.resource_prefix}-{service_name}-execution-role",
            assume_role_policy=self._get_assume_role_policy("ecs-tasks.amazonaws.com"),
            inline_policy=[
                {
                    "name": f"{service_name}-execution-policy",
                    "policy": json.dumps(execution_role_policy),
                }
            ],
            tags=self.tags,
        )

        # Attach ECS execution role policy
        IamRolePolicyAttachment(
            self,
            f"{service_name}-execution-policy",
            role=execution_role.name,
            policy_arn="arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy",
        )

        return execution_role

    def _create_task_role(self, service_name: str, statements: List[dict]) -> IamRole:
        """Creates a task role for a specific service."""
        task_policy = {"Version": "2012-10-17", "Statement": statements}

        return IamRole(
            self,
            f"{service_name}-task-role",
            name=f"{self.resource_prefix}-{service_name}-task-role",
            assume_role_policy=self._get_assume_role_policy("ecs-tasks.amazonaws.com"),
            inline_policy=[
                {
                    "name": f"{service_name}-task-policy",
                    "policy": json.dumps(task_policy),
                }
            ]
            if statements
            else None,
            tags=self.tags,
        )

    def add_policy_to_task_role(
        self, service_name: str, policy_name: str, policy_document: dict
    ) -> None:
        """
        Adds a new policy to a service's task role.

        Args:
            service_name: Name of the service
            policy_name: Name of the policy to add
            policy_document: Policy document as a dictionary
        """
        if service_name not in self.service_task_roles:
            raise ValueError(f"No task role found for service: {service_name}")

        IamRolePolicy(
            self,
            f"{service_name}-{policy_name}",
            name=f"{self.resource_prefix}-{service_name}-{policy_name}",
            role=self.service_task_roles[service_name].name,
            policy=json.dumps(policy_document),
        )

    def add_policy_to_execution_role(
        self, service_name: str, policy_name: str, policy_document: dict
    ) -> None:
        """
        Adds a new policy to a service's execution role.

        Args:
            service_name: Name of the service
            policy_name: Name of the policy to add
            policy_document: Policy document as a dictionary
        """
        if service_name not in self.service_execution_roles:
            raise ValueError(f"No execution role found for service: {service_name}")

        IamRolePolicy(
            self,
            f"{service_name}-{policy_name}",
            name=f"{self.resource_prefix}-{service_name}-{policy_name}",
            role=self.service_execution_roles[service_name].name,
            policy=json.dumps(policy_document),
        )

    def _create_role_outputs(self) -> None:
        """Creates TerraformOutputs for all roles."""
        TerraformOutput(
            self,
            "instance-role-arn",
            value=self.instance_role.arn,
            description="Instance Role ARN",
        )

        for service_name in self.service_execution_roles:
            TerraformOutput(
                self,
                f"{service_name}-execution-role-arn",
                value=self.service_execution_roles[service_name].arn,
                description=f"{service_name} Execution Role ARN",
            )

            TerraformOutput(
                self,
                f"{service_name}-task-role-arn",
                value=self.service_task_roles[service_name].arn,
                description=f"{service_name} Task Role ARN",
            )

    @staticmethod
    def _get_assume_role_policy(service: str) -> str:
        """Returns the assume role policy for a given service."""
        return json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Action": "sts:AssumeRole",
                        "Principal": {"Service": service},
                        "Effect": "Allow",
                    }
                ],
            }
        )
