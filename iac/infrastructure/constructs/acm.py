from constructs import Construct
from cdktf import Fn, Token
from cdktf_cdktf_provider_aws.acm_certificate import AcmCertificate
from cdktf_cdktf_provider_aws.acm_certificate_validation import AcmCertificateValidation
from cdktf_cdktf_provider_aws.route53_record import Route53Record
from cdktf_cdktf_provider_aws.data_aws_route53_zone import DataAwsRoute53Zone


class AcmRoute53Construct(Construct):
    """
    A construct for managing ACM certificates and optionally Route53 DNS records.

    This construct handles:
    1. Looking up an existing Route53 hosted zone.
    2. Creating an ACM certificate for a specific subdomain.
    3. Creating DNS validation records to prove domain ownership.
    4. Validating the certificate.
    5. Optionally, creating an alias record to point the subdomain to a target (e.g., ALB, API Gateway).

    Attributes:
        hosted_zone (DataAwsRoute53Zone): Reference to the existing Route53 hosted zone.
        certificate (AcmCertificate): The ACM certificate for the domain.
        certificate_validation (AcmCertificateValidation): The certificate validation resource.
        alias_record (Route53Record, optional): The A record pointing to the target, if created.
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        domain_name: str,
        subdomain: str,
        tags: dict,
        create_alias_record: bool = True,
        alias_target_dns_name: str = None,
        alias_target_zone_id: str = None,
    ) -> None:
        super().__init__(scope, id)

        self.alias_record = None

        # Get the hosted zone
        self.hosted_zone = DataAwsRoute53Zone(
            self,
            "hosted-zone",
            name=domain_name,
            private_zone=False,
        )

        fqdn = f"{subdomain}.{domain_name}"

        # Create ACM certificate
        self.certificate = AcmCertificate(
            self,
            "certificate",
            domain_name=fqdn,
            validation_method="DNS",
            tags=tags,
        )
        
        validation_option_list = self.certificate.domain_validation_options
        
        first_validation_option = Fn.element(validation_option_list, 0)

        validation_record_name = Token.as_string(Fn.lookup(first_validation_option, "resource_record_name", ""))
        validation_record_type = Token.as_string(Fn.lookup(first_validation_option, "resource_record_type", ""))
        validation_record_value = Token.as_string(Fn.lookup(first_validation_option, "resource_record_value", ""))

        dns_validation_record = Route53Record(
            self,
            "dns-validation-record",
            zone_id=Token.as_string(self.hosted_zone.zone_id),
            name=validation_record_name,
            type=validation_record_type,
            records=[validation_record_value],
            ttl=60,
            allow_overwrite=True
        )

        # Create certificate validation
        self.certificate_validation = AcmCertificateValidation(
            self,
            "certificate-validation",
            certificate_arn=self.certificate.arn,
            validation_record_fqdns=[dns_validation_record.fqdn],
        )

        if create_alias_record:
            if not alias_target_dns_name or not alias_target_zone_id:
                raise ValueError(
                    "If create_alias_record is True, alias_target_dns_name and alias_target_zone_id must be provided."
                )
            self.alias_record = Route53Record(
                self,
                "alias-record",
                zone_id=Token.as_string(self.hosted_zone.zone_id),
                name=fqdn,
                type="A",
                alias={
                    "name": alias_target_dns_name,
                    "zone_id": alias_target_zone_id,
                    "evaluate_target_health": True,
                },
            )
