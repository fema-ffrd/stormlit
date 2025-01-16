from constructs import Construct
from cdktf import Fn, Token
from cdktf_cdktf_provider_aws.acm_certificate import AcmCertificate
from cdktf_cdktf_provider_aws.acm_certificate_validation import AcmCertificateValidation
from cdktf_cdktf_provider_aws.route53_record import Route53Record
from cdktf_cdktf_provider_aws.data_aws_route53_zone import DataAwsRoute53Zone


class AcmRoute53Construct(Construct):
    """
    A construct for managing ACM certificates and Route53 DNS records.
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
            name=Token.as_string(Fn.lookup(
                Fn.element(self.certificate.domain_validation_options, 0),
                "resource_record_name",
                ""
            )),
            type=Token.as_string(Fn.lookup(
                Fn.element(self.certificate.domain_validation_options, 0),
                "resource_record_type",
                ""
            )),
            records=[
                Token.as_string(Fn.lookup(
                    Fn.element(self.certificate.domain_validation_options, 0),
                    "resource_record_value",
                    ""
                ))
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