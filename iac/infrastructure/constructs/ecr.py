import json
from constructs import Construct
from cdktf_cdktf_provider_aws.ecr_repository import (
    EcrRepository,
    EcrRepositoryImageScanningConfiguration,
    EcrRepositoryEncryptionConfiguration,
)
from cdktf_cdktf_provider_aws.ecr_lifecycle_policy import EcrLifecyclePolicy


class EcrConstruct(Construct):
    """
    A Construct for creating an Elastic Container Registry (ECR) repository and applying a lifecycle policy.

    This construct facilitates the setup of an ECR repository for storing and managing container images.
    The repository is configured with image scanning for vulnerabilities and encryption using AWS Key Management
    Service (KMS). A lifecycle policy is applied to manage image retention and cleanup.

    Attributes:
        streamlit_repository (EcrRepository): ECR repository for the Streamlit application.

    Parameters:
        scope (Construct): The scope in which this construct is defined.
        id (str): The unique identifier of the construct.
        project_prefix (str): A prefix for project-related resource names to ensure uniqueness.
        environment (str): The environment name (e.g., `development`, `production`) to differentiate resources.
        tags (dict): A dictionary of tags to apply to all resources created by this construct.

    Methods:
        __init__(self, scope, id, ...): Initializes the ECR repository and applies the lifecycle policy.
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        project_prefix: str,
        environment: str,
        tags: dict,
    ) -> None:
        super().__init__(scope, id)

        resource_prefix = f"{project_prefix}-{environment}"

        # Create ECR repository for Streamlit app
        self.streamlit_repository = EcrRepository(
            self,
            "streamlit-repo",
            name=f"{resource_prefix}-streamlit",
            image_tag_mutability="MUTABLE",
            force_delete=True if environment == "development" else False,
            image_scanning_configuration=EcrRepositoryImageScanningConfiguration(
                scan_on_push=True
            ),
            encryption_configuration=[
                EcrRepositoryEncryptionConfiguration(encryption_type="KMS")
            ],
            tags=tags,
        )

        # Add lifecycle policy
        lifecycle_policy = {
            "rules": [
                {
                    "rulePriority": 1,
                    "description": "Keep last 5 images",
                    "selection": {
                        "tagStatus": "tagged",
                        "tagPatternList": ["*"],
                        "countType": "imageCountMoreThan",
                        "countNumber": 5,
                    },
                    "action": {"type": "expire"},
                },
                {
                    "rulePriority": 2,
                    "description": "Expire untagged images older than 1 day",
                    "selection": {
                        "tagStatus": "untagged",
                        "countType": "sinceImagePushed",
                        "countUnit": "days",
                        "countNumber": 1,
                    },
                    "action": {"type": "expire"},
                },
            ]
        }

        EcrLifecyclePolicy(
            self,
            "streamlit-lifecycle-policy",
            repository=self.streamlit_repository.name,
            policy=json.dumps(lifecycle_policy),
        )
