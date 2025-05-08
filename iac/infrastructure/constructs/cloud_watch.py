from constructs import Construct
from cdktf_cdktf_provider_aws.cloudwatch_log_group import CloudwatchLogGroup


class CloudWatchConstruct(Construct):
    """
    A construct for creating CloudWatch Log Groups to centralize ECS service logs.

    This construct creates and configures CloudWatch Log Groups for different ECS services,
    enabling centralized logging and monitoring. Each service gets its own log group with
    configurable retention periods and consistent naming conventions.

    The construct creates log groups for:
    - STAC API service (/ecs/{prefix}-stac-api)
    - Streamlit application (/ecs/{prefix}-stormlit)

    Attributes:
        stac_api_log_group (CloudwatchLogGroup): Log group for the STAC API service
        streamlit_log_group (CloudwatchLogGroup): Log group for the Streamlit application

    Parameters:
        scope (Construct): The scope in which this construct is defined
        id (str): The scoped construct ID
        project_prefix (str): Prefix for resource names (e.g., "project-name")
        environment (str): Environment name (e.g., "prod", "dev")
        tags (dict): Tags to apply to the created log groups

    Example:
        ```python
        CloudWatchConstruct(
            self,
            "cloudwatch",
            project_prefix="myapp",
            environment="prod",
            tags={"Environment": "production"}
        )
        ```

    Notes:
        - Log groups are created with a 30-day retention period
        - Log group names follow the pattern: /ecs/{project_prefix}-{environment}-{service}
        - Log groups automatically integrate with ECS task definitions when properly referenced
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

        # Create log groups for each service
        self.streamlit_log_group = CloudwatchLogGroup(
            self,
            "stormlit-logs",
            name=f"/ecs/{resource_prefix}-stormlit",
            retention_in_days=30,
            tags=tags,
        )

        self.stac_api_log_group = CloudwatchLogGroup(
            self,
            "stac-api-logs",
            name=f"/ecs/{resource_prefix}-stac-api",
            retention_in_days=30,
            tags=tags,
        )
