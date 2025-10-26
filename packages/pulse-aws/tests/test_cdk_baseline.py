from __future__ import annotations

import aws_cdk as cdk
from aws_cdk.assertions import Template
from pulse_aws.cdk.baseline import BaselineStack


def synth(**kwargs) -> Template:
	app = cdk.App()
	stack = BaselineStack(
		app,
		"TestBaseline",
		env_name="dev",
		allowed_ingress_cidrs=["0.0.0.0/0"],
		**kwargs,
	)
	return Template.from_stack(stack)


def test_stack_uses_imported_certificate_when_arn_provided():
	template = synth(
		certificate_arn="arn:aws:acm:us-east-1:123456789012:certificate/external",
		domains=["pulse.example.com"],
	)

	template.resource_count_is("AWS::CertificateManager::Certificate", 0)
	outputs = template.to_json()["Outputs"]
	assert (
		outputs["CertificateArn"]["Value"]
		== "arn:aws:acm:us-east-1:123456789012:certificate/external"
	)
	assert "CertificateValidationRecords" not in outputs


def test_stack_mints_certificate_and_exposes_validation_records():
	template = synth(
		domains=["pulse.example.com", "www.pulse.example.com"],
	)

	template.resource_count_is("AWS::CertificateManager::Certificate", 1)
	outputs = template.to_json()["Outputs"]
	value = outputs["CertificateValidationRecords"]["Value"]
	assert isinstance(value, dict) and "Fn::GetAtt" in value
	assert value["Fn::GetAtt"][1] == "Certificate.DomainValidationOptions"
