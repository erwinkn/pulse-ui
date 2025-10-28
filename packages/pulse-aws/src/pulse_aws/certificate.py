from __future__ import annotations

import asyncio
import ipaddress
import json
import socket
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import boto3

from pulse_aws.reporting import DeploymentContext, Reporter, create_context


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


def _prepare_context(
	context: DeploymentContext | None,
	reporter: Reporter | None,
) -> DeploymentContext:
	"""Normalize context and reporter inputs."""
	if context is None:
		return create_context(reporter=reporter)
	if reporter is not None:
		context.reporter = reporter
	return context


def _emit_dns_instructions(config: DnsConfiguration, reporter: Reporter) -> None:
	"""Display DNS instructions using the configured reporter."""
	for line in config.format_for_display().splitlines():
		if line:
			reporter.info(line)
		else:
			reporter.blank()


def _resolve_ip_addresses(host: str) -> set[str]:
	"""Resolve a hostname to all associated IPv4/IPv6 addresses."""
	addresses: set[str] = set()
	try:
		results = socket.getaddrinfo(host, None)
	except (socket.gaierror, socket.herror):
		return addresses

	for result in results:
		sockaddr = result[4]
		if sockaddr:
			addresses.add(sockaddr[0])
	return addresses


_CLOUDFLARE_IPV4_RANGES = tuple(
	ipaddress.ip_network(cidr)
	for cidr in [
		"173.245.48.0/20",
		"103.21.244.0/22",
		"103.22.200.0/22",
		"103.31.4.0/22",
		"141.101.64.0/18",
		"108.162.192.0/18",
		"190.93.240.0/20",
		"188.114.96.0/20",
		"197.234.240.0/22",
		"198.41.128.0/17",
		"162.158.0.0/15",
		"104.16.0.0/13",
		"104.24.0.0/14",
		"172.64.0.0/13",
		"131.0.72.0/22",
	]
)
_CLOUDFLARE_IPV6_RANGES = tuple(
	ipaddress.ip_network(cidr)
	for cidr in [
		"2400:cb00::/32",
		"2606:4700::/32",
		"2803:f800::/32",
		"2405:b500::/32",
		"2405:8100::/32",
		"2a06:98c0::/29",
		"2c0f:f248::/32",
	]
)


def _is_cloudflare_ip(address: str) -> bool:
	"""Check if an IP address belongs to Cloudflare's anycast network."""
	try:
		ip = ipaddress.ip_address(address)
	except ValueError:
		return False

	networks = _CLOUDFLARE_IPV6_RANGES if ip.version == 6 else _CLOUDFLARE_IPV4_RANGES
	return any(ip in network for network in networks)


def domain_uses_cloudflare_proxy(
	domain: str, *, resolved_ips: set[str] | None = None
) -> bool:
	"""Return True if all resolved IPs map to Cloudflare's proxy network."""
	ips = resolved_ips if resolved_ips is not None else _resolve_ip_addresses(domain)
	if not ips:
		return False
	return all(_is_cloudflare_ip(ip) for ip in ips)


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
	announce: bool = True,
	context: DeploymentContext | None = None,
	reporter: Reporter | None = None,
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
	    context: Optional deployment context to control reporting behaviour
	    reporter: Optional reporter override (defaults to CLI/CI auto-detection)

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

	context = _prepare_context(context, reporter)
	reporter = context.reporter

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
			if announce:
				reporter.info(
					f"ℹ️ Using existing ACM certificate for {primary_domain}: {cert_summary['CertificateArn']} (status: {cert['Status']})"
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
			if announce and cert["Status"] == "PENDING_VALIDATION" and dns_config:
				reporter.blank()
				_emit_dns_instructions(dns_config, reporter)
				reporter.blank()
				reporter.success(f"Certificate ARN: {cert_summary['CertificateArn']}")
				reporter.blank()

			if wait and cert["Status"] != "ISSUED":
				return await _wait_for_certificate_issuance(
					acm_client,
					result.arn,
					poll_interval,
					announce=announce,
					reporter=reporter if announce else None,
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
	if announce:
		reporter.success(
			f"Requested ACM certificate for {primary_domain}: {certificate_arn}"
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
	if announce:
		reporter.blank()
		_emit_dns_instructions(dns_config, reporter)
		reporter.blank()
		reporter.success(f"Certificate ARN: {certificate_arn}")
		reporter.blank()

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
			announce=announce,
			reporter=reporter if announce else None,
		)

	return result


async def _wait_for_certificate_issuance(
	acm_client: Any,
	certificate_arn: str,
	poll_interval: float,
	timeout: float | None = None,
	announce: bool = True,
	reporter: Reporter | None = None,
) -> AcmCertificate:
	"""Wait for an ACM certificate to transition from PENDING_VALIDATION to ISSUED."""
	if announce and reporter is not None:
		reporter.info(
			"⏳ Waiting for certificate validation (add DNS records in your provider)..."
		)
		reporter.blank()

	start_time = asyncio.get_event_loop().time()
	while True:
		cert_detail = acm_client.describe_certificate(CertificateArn=certificate_arn)
		cert = cert_detail["Certificate"]
		status = cert["Status"]

		if status == "ISSUED":
			if announce and reporter is not None:
				reporter.success("Certificate issued!")
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
	expected_ips = _resolve_ip_addresses(expected_target)
	if not expected_ips:
		# Can't resolve expected target - probably temporary issue, don't block deployment
		return None

	domain_ips = _resolve_ip_addresses(domain)
	if not domain_ips:
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

	# Domain resolves but to the wrong target; handle Cloudflare proxy scenario gracefully
	if domain_uses_cloudflare_proxy(domain, resolved_ips=domain_ips):
		return None

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
	"domain_uses_cloudflare_proxy",
	"ensure_acm_certificate",
	"parse_acm_validation_records",
]
