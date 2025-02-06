from constructs import Construct
from cdktf_cdktf_provider_random.password import Password
from cdktf_cdktf_provider_random.provider import RandomProvider


class RandomPasswordConstruct(Construct):
    """
    A construct that generates random passwords for the database and application.

    Attributes:
        db_admin_password (Password): The randomly generated password for the database admin user.
        pgstac_admin_password (Password): The randomly generated password for the PgStac admin user.
        pgstac_ingest_password (Password): The randomly generated password for the PgStac ingest user.
        pgstac_read_password (Password): The randomly generated password for the PgStac read-only user.

    Note:
        For mor information on the PgSTAC roles see https://stac-utils.github.io/pgstac/pgstac/
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
