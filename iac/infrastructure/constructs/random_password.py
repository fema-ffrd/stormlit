from constructs import Construct
from cdktf_cdktf_provider_random.password import Password
from cdktf_cdktf_provider_random.provider import RandomProvider


class RandomPasswordConstruct(Construct):
    """
    A construct for generating secure random passwords for database users.

    This construct creates secure random passwords for database and PgSTAC roles using the
    CDKTF random provider. It generates passwords for:
    1. Database admin user
    2. PgSTAC admin user
    3. PgSTAC ingest user
    4. PgSTAC read-only user

    Each password is configured with:
    - Configurable minimum length (default: 16 characters)
    - Optional special characters
    - Custom set of allowed special characters
    - Secure random generation

    Attributes:
        db_admin_password (Password): Random password for database admin
        pgstac_admin_password (Password): Random password for PgSTAC admin
        pgstac_ingest_password (Password): Random password for PgSTAC ingest user
        pgstac_read_password (Password): Random password for PgSTAC read-only user

    Parameters:
        scope (Construct): The scope in which this construct is defined
        id (str): The scoped construct ID
        min_length (int, optional): Minimum password length. Defaults to 16.
        special (bool, optional): Include special characters. Defaults to True.

    Example:
        ```python
        passwords = RandomPasswordConstruct(
            self,
            "random-passwords",
            min_length=20,
            special=True
        )

        # Access generated passwords
        admin_pass = passwords.db_admin_password.result
        pgstac_pass = passwords.pgstac_admin_password.result
        ```

    Notes:
        - Uses CDKTF random provider for secure generation
        - Restricts special characters to: !#$%&*()-_=+[]{}<>:?
        - Passwords are only generated once and stored in Terraform state
        - Results should be stored securely in AWS Secrets Manager
        - Password values are sensitive and handled accordingly
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
        self.db_admin_password = Password(
            self,
            "db-admin-password",
            length=min_length,
            special=special,
            override_special="!#$%&*()-_=+[]{}<>:?",
        )

        # Generate PgStac Database Passwords
        self.pgstac_admin_password = Password(
            self,
            "pgstac-admin-password",
            length=min_length,
            special=special,
            override_special="!#$%&*()-_=+[]{}<>:?",
        )
        self.pgstac_ingest_password = Password(
            self,
            "pgstac-ingest-password",
            length=min_length,
            special=special,
            override_special="!#$%&*()-_=+[]{}<>:?",
        )
        self.pgstac_read_password = Password(
            self,
            "pgstac-read-password",
            length=min_length,
            special=special,
            override_special="!#$%&*()-_=+[]{}<>:?",
        )
