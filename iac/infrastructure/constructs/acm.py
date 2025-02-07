from constructs import Construct
from cdktf import Fn, Token
from cdktf_cdktf_provider_aws.acm_certificate import AcmCertificate
from cdktf_cdktf_provider_aws.acm_certificate_validation import AcmCertificateValidation
from cdktf_cdktf_provider_aws.route53_record import Route53Record
from cdktf_cdktf_provider_aws.data_aws_route53_zone import DataAwsRoute53Zone


class AcmRoute53Construct(Construct):
    """
    A construct for managing ACM certificates and Route53 DNS records.

    This construct handles the creation and validation of SSL/TLS certificates through AWS Certificate Manager (ACM)
    and sets up the necessary DNS records in Route53. It automates the process of:
    1. Looking up an existing Route53 hosted zone
    2. Creating an ACM certificate for a specific subdomain
    3. Creating DNS validation records to prove domain ownership
    4. Validating the certificate
    5. Creating an alias record to point the subdomain to an Application Load Balancer

    Attributes:
        hosted_zone (DataAwsRoute53Zone): Reference to the existing Route53 hosted zone
        certificate (AcmCertificate): The ACM certificate for the domain
        certificate_validation (AcmCertificateValidation): The certificate validation resource
        alias_record (Route53Record): The A record pointing to the ALB

    Parameters:
        scope (Construct): The scope in which this construct is defined
        id (str): The scoped construct ID
        domain_name (str): The apex domain name (e.g., "example.com")
        subdomain (str): The subdomain prefix (e.g., "api" for "api.example.com")
        alb_dns_name (str): The DNS name of the Application Load Balancer
        alb_zone_id (str): The hosted zone ID of the Application Load Balancer
        tags (dict): Tags to apply to the created resources

    Example:
        ```python
        AcmRoute53Construct(
            self,
            "acm",
            domain_name="example.com",
            subdomain="api",
            alb_dns_name=alb.dns_name,
            alb_zone_id=alb.zone_id,
            tags={"Environment": "production"}
        )
        ```
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        domain_name: str,
        subdomain: str,
        alb_dns_name: str,
        alb_zone_id: str,
        tags: dict,
    ) -> None:
        super().__init__(scope, id)

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

        # Create DNS validation record
        validation_record = Route53Record(
            self,
            "validation-record",
            zone_id=self.hosted_zone.zone_id,
            name=Token.as_string(
                Fn.lookup(
                    Fn.element(self.certificate.domain_validation_options, 0),
                    "resource_record_name",
                    "",
                )
            ),
            type=Token.as_string(
                Fn.lookup(
                    Fn.element(self.certificate.domain_validation_options, 0),
                    "resource_record_type",
                    "",
                )
            ),
            records=[
                Token.as_string(
                    Fn.lookup(
                        Fn.element(self.certificate.domain_validation_options, 0),
                        "resource_record_value",
                        "",
                    )
                )
            ],
            ttl=60,
        )

        # Create certificate validation
        self.certificate_validation = AcmCertificateValidation(
            self,
            "certificate-validation",
            certificate_arn=self.certificate.arn,
            validation_record_fqdns=[validation_record.fqdn],
        )

        # Create A record for the subdomain pointing to the ALB
        self.alias_record = Route53Record(
            self,
            "alias-record",
            zone_id=self.hosted_zone.zone_id,
            name=fqdn,
            type="A",
            alias={
                "name": alb_dns_name,
                "zone_id": alb_zone_id,
                "evaluate_target_health": True,
            },
        )
