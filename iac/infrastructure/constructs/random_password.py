from constructs import Construct
from cdktf_cdktf_provider_random.password import Password
from cdktf_cdktf_provider_random.provider import RandomProvider


class RandomPasswordConstruct(Construct):
    """
    A Construct for generating secure random passwords using the random provider.

    This construct manages the creation of cryptographically secure random passwords
    for various services like databases and application credentials. It ensures passwords
    meet specified complexity requirements and length constraints.

    Attributes:
        database_password (Password): The generated random password for database access.
        keycloak_password (Password): The generated random password for Keycloak admin.
        streamlit_password (Password): The generated random password for Streamlit admin.

    Parameters:
        scope (Construct): The scope in which this construct is defined.
        id (str): The unique identifier of the construct.
        min_length (int): Minimum length for generated passwords.
        special (bool): Whether to include special characters in passwords.

    Methods:
        __init__(self, scope, id, ...): Initializes the random password generator.
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        min_length: int = 16,
        special: bool = True,
    ) -> None:
        super().__init__(scope, id)

        # Configure Random Provider
        RandomProvider(self, "random")

        # Generate Database Password
        self.database_password = Password(
            self,
            "database-password",
            length=min_length,
            special=special,
            override_special="!#$%&*()-_=+[]{}<>:?",  # Safer special chars for passwords
        )

        # Generate Keycloak Password
        self.keycloak_password = Password(
            self,
            "keycloak-password",
            length=min_length,
            special=special,
            override_special="!#$%&*()-_=+[]{}<>:?",
        )

        # Generate Streamlit Password
        self.streamlit_password = Password(
            self,
            "streamlit-password",
            length=min_length,
            special=special,
            override_special="!#$%&*()-_=+[]{}<>:?",
        )