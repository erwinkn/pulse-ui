from __future__ import annotations

import json

import aws_cdk as cdk
from aws_cdk.assertions import Template
from pulse_aws.cdk.baseline import BaselineStack
from pulse_aws.certificate import parse_acm_validation_records


def synth(**kwargs) -> Template:
	app = cdk.App()
	stack = BaselineStack(
		app,
		"TestBaseline",
		deployment_name="dev",
		certificate_arn="arn:aws:acm:us-east-1:123456789012:certificate/test",
		allowed_ingress_cidrs=["0.0.0.0/0"],
		**kwargs,
	)
	return Template.from_stack(stack)


def test_stack_with_certificate_arn():
	template = synth()

	outputs = template.to_json()["Outputs"]
	assert (
		outputs["CertificateArn"]["Value"]
		== "arn:aws:acm:us-east-1:123456789012:certificate/test"
	)
	# No custom domain or validation records in baseline
	assert "CustomDomainName" not in outputs
	assert "CertificateValidationRecords" not in outputs


def test_parse_acm_validation_records():
	"""Test parsing ACM certificate validation records into DNS configuration."""
	validation_json = json.dumps(
		[
			{
				"DomainName": "pulse.example.com",
				"ValidationDomain": "pulse.example.com",
				"ValidationStatus": "PendingValidation",
				"ResourceRecord": {
					"Name": "_abc123.pulse.example.com.",
					"Type": "CNAME",
					"Value": "_xyz789.acm-validations.aws.",
				},
			},
			{
				"DomainName": "www.pulse.example.com",
				"ValidationDomain": "pulse.example.com",
				"ValidationStatus": "PendingValidation",
				"ResourceRecord": {
					"Name": "_def456.www.pulse.example.com.",
					"Type": "CNAME",
					"Value": "_uvw123.acm-validations.aws.",
				},
			},
		]
	)

	config = parse_acm_validation_records("pulse.example.com", validation_json)

	assert config.domain_name == "pulse.example.com"
	assert len(config.records) == 2
	assert config.records[0].name == "_abc123.pulse.example.com."
	assert config.records[0].type == "CNAME"
	assert config.records[0].value == "_xyz789.acm-validations.aws."
	assert (
		config.records[0].description is not None
		and "pulse.example.com" in config.records[0].description
	)

	# Test formatted output
	output = config.format_for_display()
	assert "🔗 Configure DNS for pulse.example.com" in output
	assert "_abc123.pulse.example.com." in output
	assert "_xyz789.acm-validations.aws." in output
