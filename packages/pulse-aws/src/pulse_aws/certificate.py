from __future__ import annotations

import asyncio
import json
import socket
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import boto3


class CertificateError(RuntimeError):
	"""Raised when certificate operations fail."""


@dataclass(slots=True)
class DnsRecord:
	"""Represents a single DNS record to configure."""

	name: str
	type: str
	value: str
	description: str | None = None

	def format_for_display(self) -> str:
		"""Format the DNS record for user-friendly display."""
		desc = f" ({self.description})" if self.description else ""
		return f"  • Type: {self.type}\n    Name: {self.name}\n    Value: {self.value}{desc}"


@dataclass(slots=True)
class DnsConfiguration:
	"""DNS configuration needed to make the deployment work."""

	domain_name: str
	records: list[DnsRecord]

	def format_for_display(self) -> str:
		"""Generate Vercel-style DNS configuration instructions."""
		lines = [
			f"🔗 Configure DNS for {self.domain_name}",
			"",
			"Add the following records to your DNS provider:",
			"",
		]
		for record in self.records:
			lines.append(record.format_for_display())
			lines.append("")
		lines.append(
			"Once the records are added, your domain will be live within a few minutes."
		)
		return "\n".join(lines)


@dataclass(slots=True)
class AcmCertificate:
	"""ACM certificate with optional DNS validation records."""

	arn: str
	status: str  # PENDING_VALIDATION, ISSUED, FAILED, etc.
	dns_configuration: DnsConfiguration | None = None


def parse_acm_validation_records(
	domain_name: str,
	validation_records_json: str,
) -> DnsConfiguration:
	"""Parse ACM certificate validation records and return formatted DNS configuration.

	Validation records from ACM's DescribeCertificate have structure:
	[
		{
			"DomainName": "example.com",
			"ValidationDomain": "example.com",
			"ValidationStatus": "PendingValidation",
			"ResourceRecord": {
				"Name": "_xxxx.example.com.",
				"Type": "CNAME",
				"Value": "_yyyy.acm-validations.aws."
			}
		},
		...
	]
	"""
	try:
		records = json.loads(validation_records_json)
	except (json.JSONDecodeError, TypeError) as exc:
		msg = f"Invalid validation records format: {validation_records_json}"
		raise CertificateError(msg) from exc

	dns_records: list[DnsRecord] = []
	for record in records:
		if "ResourceRecord" not in record:
			continue

		rr = record["ResourceRecord"]
		dns_records.append(
			DnsRecord(
				name=rr["Name"],
				type=rr["Type"],
				value=rr["Value"],
				description=f"Certificate validation for {record.get('DomainName', domain_name)}",
			)
		)

	return DnsConfiguration(
		domain_name=domain_name,
		records=dns_records,
	)


async def ensure_acm_certificate(
	domains: str | Sequence[str],
	*,
	wait: bool = True,
	poll_interval: float = 5.0,
	timeout: float | None = None,
) -> AcmCertificate:
	"""Mint an ACM certificate for the given domains with DNS validation.

	Returns the certificate ARN and DNS configuration instructions.
	When a new certificate is created, DNS instructions are printed automatically.

	    IMPORTANT: This function must run BEFORE deploying the baseline CloudFormation stack.
	    AWS does not allow attaching a PENDING_VALIDATION certificate to an ALB listener -
	    the certificate must be ISSUED first. This requires:
	    1. Requesting the certificate (this function)
	    2. Adding DNS validation records to your DNS provider
	    3. Waiting 5-10 minutes for AWS to validate and issue the certificate
	    4. Only then deploying the baseline stack with the certificate ARN

	Args:
	    domains: Domain name or list of domain names
	    wait: Wait for the certificate to be ISSUED (not just PENDING_VALIDATION). Default: True.
	        Requires DNS records to be added to your DNS provider first.
	    poll_interval: How often to check certificate status (in seconds)
	    timeout: If provided and `wait` is True, maximum seconds to wait for ISSUANCE.
	        If not provided and `wait` is True, waits indefinitely for issuance.

	    Example::

	            cert = await ensure_acm_certificate(["api.example.com"])
	            # Output:
	            # 🔗 Configure DNS for api.example.com
	            # ...
	            #
	            # Certificate ARN: arn:aws:acm:...
	            #
	            # Or wait for issuance:
	            cert = await ensure_acm_certificate(["api.example.com"], wait=True)
	            # (after DNS records are added)
	"""
	if not domains:
		msg = "At least one domain is required"
		raise ValueError(msg)

	if isinstance(domains, str):
		domains = [domains]
	else:
		domains = list(domains)

	sts = boto3.client("sts")
	region = sts.meta.region_name

	if not region or region == "aws-global":
		msg = (
			"No valid AWS region configured. Set it via:\n"
			"  • AWS_REGION environment variable\n"
			"  • ~/.aws/config: [profile <name>]\\n    region = us-east-1\n"
			"  • AWS_DEFAULT_REGION environment variable"
		)
		raise CertificateError(msg)

	acm_client = boto3.client("acm", region_name=region)

	primary_domain = domains[0]

	# Check if a certificate already exists for this domain
	response = acm_client.list_certificates(
		CertificateStatuses=["PENDING_VALIDATION", "ISSUED"],
	)

	for cert_summary in response.get("CertificateSummaryList", []):
		if cert_summary["DomainName"] == primary_domain:
			# Certificate exists, retrieve its details
			cert_detail = acm_client.describe_certificate(
				CertificateArn=cert_summary["CertificateArn"],
			)
			cert = cert_detail["Certificate"]
			validation_records = cert.get("DomainValidationOptions", [])

			# Always inform the user about the existing certificate and its status
			print(
				f"ℹ️ Using existing ACM certificate for {primary_domain}: {cert_summary['CertificateArn']} (status: {cert['Status']})",
				file=sys.stderr,
			)

			dns_config = None
			if validation_records:
				dns_config = parse_acm_validation_records(
					primary_domain,
					json.dumps(validation_records),
				)

			result = AcmCertificate(
				arn=cert_summary["CertificateArn"],
				status=cert["Status"],
				dns_configuration=dns_config,
			)

			# If certificate is pending validation, show DNS instructions before any waiting
			if cert["Status"] == "PENDING_VALIDATION" and dns_config:
				print()
				print(dns_config.format_for_display())
				print()
				print(f"✅ Certificate ARN: {cert_summary['CertificateArn']}")
				print()

			if wait and cert["Status"] != "ISSUED":
				return await _wait_for_certificate_issuance(
					acm_client,
					result.arn,
					poll_interval,
				)

			return result

	# Create new certificate
	request_params: dict[str, Any] = {
		"DomainName": primary_domain,
		"ValidationMethod": "DNS",
	}
	if len(domains) > 1:
		request_params["SubjectAlternativeNames"] = domains[1:]

	cert_response = acm_client.request_certificate(**request_params)

	certificate_arn = cert_response["CertificateArn"]

	# Inform that a new certificate request was created
	print(
		f"✅ Requested ACM certificate for {primary_domain}: {certificate_arn}",
		file=sys.stderr,
	)

	# Get validation records - may need to wait for ResourceRecord to be populated (silent)
	start_time = asyncio.get_event_loop().time()
	check_interval = 2.0

	while True:
		cert_detail = acm_client.describe_certificate(CertificateArn=certificate_arn)
		cert = cert_detail["Certificate"]
		validation_records = cert.get("DomainValidationOptions", [])

		# Check if ResourceRecord is present
		if validation_records and any(
			"ResourceRecord" in rec for rec in validation_records
		):
			break

		elapsed = asyncio.get_event_loop().time() - start_time
		# Bound the wait for DNS validation records population to a reasonable fixed window
		records_timeout = 60.0
		if elapsed >= records_timeout:
			msg = (
				f"Certificate {certificate_arn} validation records did not populate after {records_timeout:.0f} seconds. "
				"Try running this again in a minute."
			)
			raise CertificateError(msg)

		await asyncio.sleep(check_interval)

	dns_config = parse_acm_validation_records(
		primary_domain,
		json.dumps(validation_records),
	)

	# Print DNS instructions by default for new certificates
	print()
	print(dns_config.format_for_display())
	print()
	print(f"✅ Certificate ARN: {certificate_arn}")
	print()

	result = AcmCertificate(
		arn=certificate_arn,
		status="PENDING_VALIDATION",
		dns_configuration=dns_config,
	)

	if wait:
		return await _wait_for_certificate_issuance(
			acm_client,
			certificate_arn,
			poll_interval,
			timeout,
		)

	return result


async def _wait_for_certificate_issuance(
	acm_client: Any,
	certificate_arn: str,
	poll_interval: float,
	timeout: float | None = None,
) -> AcmCertificate:
	"""Wait for an ACM certificate to transition from PENDING_VALIDATION to ISSUED."""
	print(
		"⏳ Waiting for certificate validation (add DNS records in your provider)...",
		file=sys.stderr,
	)
	print()

	start_time = asyncio.get_event_loop().time()
	while True:
		cert_detail = acm_client.describe_certificate(CertificateArn=certificate_arn)
		cert = cert_detail["Certificate"]
		status = cert["Status"]

		if status == "ISSUED":
			print("✅ Certificate issued!", file=sys.stderr)
			return AcmCertificate(arn=certificate_arn, status="ISSUED")

		if status == "FAILED":
			reasons = cert.get("FailureReason", "Unknown reason")
			msg = f"Certificate validation failed: {reasons}"
			raise CertificateError(msg)

		# Timeout if specified
		if timeout is not None:
			elapsed = asyncio.get_event_loop().time() - start_time
			if elapsed >= timeout:
				raise CertificateError(
					f"Timed out waiting for certificate {certificate_arn} to be ISSUED after {timeout:.0f} seconds"
				)

		await asyncio.sleep(poll_interval)


def check_domain_dns(domain: str, expected_target: str) -> DnsConfiguration | None:
	"""Check if a domain resolves to the expected target (e.g., ALB DNS name).

	Returns DnsConfiguration with the required DNS record if the domain doesn't
	resolve to the expected target, or None if it's already configured correctly.

	Args:
	    domain: The domain to check (e.g., "test.stoneware.rocks")
	    expected_target: The expected CNAME/ALIAS target (e.g., "test-alb-xxx.us-east-2.elb.amazonaws.com")

	Returns:
	    DnsConfiguration if DNS needs to be configured, None if already correct
	"""
	# Resolve the expected target to get its IPs
	try:
		expected_ips = set(socket.gethostbyname_ex(expected_target)[2])
	except (socket.gaierror, socket.herror):
		# Can't resolve expected target - probably temporary issue, don't block deployment
		return None

	# Resolve the domain to see what it currently points to
	try:
		domain_ips = set(socket.gethostbyname_ex(domain)[2])
	except (socket.gaierror, socket.herror):
		# Domain doesn't resolve - needs DNS configuration
		return DnsConfiguration(
			domain_name=domain,
			records=[
				DnsRecord(
					name=domain,
					type="CNAME",
					value=expected_target,
					description="Route traffic to Application Load Balancer",
				)
			],
		)

	# Check if any IPs match
	if domain_ips & expected_ips:
		# Domain resolves to the correct target
		return None

	# Domain resolves but to the wrong target
	return DnsConfiguration(
		domain_name=domain,
		records=[
			DnsRecord(
				name=domain,
				type="CNAME",
				value=expected_target,
				description="Route traffic to Application Load Balancer (currently points elsewhere)",
			)
		],
	)


__all__ = [
	"AcmCertificate",
	"CertificateError",
	"DnsConfiguration",
	"DnsRecord",
	"check_domain_dns",
	"ensure_acm_certificate",
	"parse_acm_validation_records",
]
