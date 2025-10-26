from __future__ import annotations

from collections.abc import Sequence

from aws_cdk import CfnOutput, RemovalPolicy, Stack, Token
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import custom_resources as cr
from constructs import Construct


class BaselineStack(Stack):
	"""Infrastructure shared by every Pulse ECS deployment."""

	def __init__(
		self,
		scope: Construct,
		construct_id: str,
		*,
		env_name: str,
		certificate_arn: str | None = None,
		domains: Sequence[str] | None = None,
		allowed_ingress_cidrs: Sequence[str] | None = None,
		**kwargs,
	) -> None:
		super().__init__(scope, construct_id, **kwargs)

		self.env_name = env_name
		self._allowed_ingress_cidrs = allowed_ingress_cidrs or ["0.0.0.0/0"]
		self._certificate_arn: str | None = None
		self._validation_records = None

		domains_list = list(domains or [])
		self.domain_name = domains_list[0] if domains_list else None

		self.vpc = ec2.Vpc(
			self,
			"PulseVpc",
			max_azs=2,
			nat_gateways=1,
			subnet_configuration=[
				ec2.SubnetConfiguration(
					name="Public",
					subnet_type=ec2.SubnetType.PUBLIC,
				),
				ec2.SubnetConfiguration(
					name="Private",
					subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
				),
			],
		)

		self.alb_security_group = ec2.SecurityGroup(
			self,
			"AlbSecurityGroup",
			vpc=self.vpc,
			description="Controls ingress to the Pulse ALB",
			allow_all_outbound=True,
		)
		for cidr in self._allowed_ingress_cidrs:
			self.alb_security_group.add_ingress_rule(
				ec2.Peer.ipv4(cidr),
				ec2.Port.tcp(80),
				"Allow HTTP",
			)
			self.alb_security_group.add_ingress_rule(
				ec2.Peer.ipv4(cidr),
				ec2.Port.tcp(443),
				"Allow HTTPS",
			)

		self.service_security_group = ec2.SecurityGroup(
			self,
			"ServiceSecurityGroup",
			vpc=self.vpc,
			description="Controls traffic from the ALB to ECS tasks",
			allow_all_outbound=True,
		)
		self.service_security_group.add_ingress_rule(
			self.alb_security_group,
			ec2.Port.tcp(80),
			"Allow HTTP from ALB",
		)
		self.service_security_group.add_ingress_rule(
			self.alb_security_group,
			ec2.Port.tcp(443),
			"Allow HTTPS from ALB",
		)
		self.service_security_group.add_ingress_rule(
			self.alb_security_group,
			ec2.Port.tcp(8000),
			"Allow Pulse default app port",
		)

		self.load_balancer = elbv2.ApplicationLoadBalancer(
			self,
			"PulseAlb",
			vpc=self.vpc,
			security_group=self.alb_security_group,
			internet_facing=True,
			load_balancer_name=f"pulse-{env_name}-alb",
		)

		acm_certificate = self._configure_certificate(certificate_arn, domains_list)

		self.listener = self.load_balancer.add_listener(
			"HttpsListener",
			port=443,
			certificates=[acm_certificate],
			open=True,
			default_action=elbv2.ListenerAction.fixed_response(
				status_code=503,
				content_type="application/json",
				message_body='{"status":"draining"}',
			),
		)

		self.log_group = logs.LogGroup(
			self,
			"PulseLogGroup",
			log_group_name=f"/aws/pulse/{env_name}/app",
			retention=logs.RetentionDays.THREE_MONTHS,
			removal_policy=RemovalPolicy.RETAIN,
		)

		self.repository = ecr.Repository(
			self,
			"PulseEcrRepository",
			repository_name=f"pulse-{env_name}",
			removal_policy=RemovalPolicy.RETAIN,
		)

		self.execution_role = iam.Role(
			self,
			"PulseExecutionRole",
			assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),  # pyright: ignore[reportArgumentType]
			description="Execution role for Pulse ECS tasks",
		)
		self.execution_role.add_managed_policy(
			iam.ManagedPolicy.from_aws_managed_policy_name(
				"service-role/AmazonECSTaskExecutionRolePolicy",
			),
		)

		self.task_role = iam.Role(
			self,
			"PulseTaskRole",
			assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
			description="Task role for Pulse ECS tasks",
		)

		self.cluster = ecs.Cluster(
			self,
			"PulseCluster",
			vpc=self.vpc,
			cluster_name=f"pulse-{env_name}",
		)
		self.cluster.connections.add_security_group(self.service_security_group)

		self._emit_outputs()

	def _emit_outputs(self) -> None:
		private_subnet_ids = ",".join(
			subnet.subnet_id for subnet in self.vpc.private_subnets
		)
		public_subnet_ids = ",".join(
			subnet.subnet_id for subnet in self.vpc.public_subnets
		)

		CfnOutput(
			self,
			"AlbDnsName",
			value=self.load_balancer.load_balancer_dns_name,
			export_name=f"pulse-{self.env_name}-alb-dns",
		)
		CfnOutput(
			self,
			"AlbHostedZoneId",
			value=self.load_balancer.load_balancer_canonical_hosted_zone_id,
			export_name=f"pulse-{self.env_name}-alb-zone",
		)
		if self.domain_name:
			CfnOutput(
				self,
				"CustomDomainName",
				value=self.domain_name,
				export_name=f"pulse-{self.env_name}-domain",
			)
		CfnOutput(
			self,
			"ListenerArn",
			value=self.listener.listener_arn,
			export_name=f"pulse-{self.env_name}-listener-arn",
		)
		CfnOutput(
			self,
			"PrivateSubnets",
			value=private_subnet_ids,
			export_name=f"pulse-{self.env_name}-private-subnets",
		)
		CfnOutput(
			self,
			"PublicSubnets",
			value=public_subnet_ids,
			export_name=f"pulse-{self.env_name}-public-subnets",
		)
		CfnOutput(
			self,
			"AlbSecurityGroupId",
			value=self.alb_security_group.security_group_id,
			export_name=f"pulse-{self.env_name}-alb-sg",
		)
		CfnOutput(
			self,
			"ServiceSecurityGroupId",
			value=self.service_security_group.security_group_id,
			export_name=f"pulse-{self.env_name}-service-sg",
		)
		CfnOutput(
			self,
			"ClusterName",
			value=self.cluster.cluster_name,
			export_name=f"pulse-{self.env_name}-cluster",
		)
		CfnOutput(
			self,
			"LogGroupName",
			value=self.log_group.log_group_name,
			export_name=f"pulse-{self.env_name}-log-group",
		)
		CfnOutput(
			self,
			"EcrRepositoryUri",
			value=self.repository.repository_uri,
			export_name=f"pulse-{self.env_name}-ecr",
		)
		CfnOutput(
			self,
			"VpcId",
			value=self.vpc.vpc_id,
			export_name=f"pulse-{self.env_name}-vpc",
		)
		if self._certificate_arn:
			CfnOutput(
				self,
				"CertificateArn",
				value=Token.as_string(self._certificate_arn),
				export_name=f"pulse-{self.env_name}-certificate-arn",
			)
		if self._validation_records is not None:
			CfnOutput(
				self,
				"CertificateValidationRecords",
				value=Token.as_string(self._validation_records),
				description=(
					"CNAME records required to validate the ACM certificate. "
					"Create these in your DNS provider."
				),
			)

	def _configure_certificate(
		self,
		certificate_arn: str | None,
		domains: Sequence[str],
	) -> acm.ICertificate:
		if not certificate_arn and not domains:
			msg = (
				"Provide certificate_arn or at least one domain to mint a certificate."
			)
			raise ValueError(msg)

		if certificate_arn:
			self._certificate_arn = certificate_arn
			return acm.Certificate.from_certificate_arn(
				self,
				"PulseImportedCertificate",
				certificate_arn,
			)

		primary = domains[0]
		sans = domains[1:]
		cfn_certificate = acm.CfnCertificate(
			self,
			"PulseCertificate",
			domain_name=primary,
			subject_alternative_names=sans or None,
			validation_method="DNS",
		)
		self._certificate_arn = cfn_certificate.ref
		self._validation_records = self._lookup_validation_records(cfn_certificate)
		return acm.Certificate.from_certificate_arn(
			self,
			"PulseIssuedCertificate",
			cfn_certificate.ref,
		)

	def _lookup_validation_records(self, certificate: acm.CfnCertificate):
		custom = cr.AwsCustomResource(
			self,
			"CertificateValidationLookup",
			on_create=cr.AwsSdkCall(
				service="ACM",
				action="describeCertificate",
				parameters={"CertificateArn": certificate.ref},
				physical_resource_id=cr.PhysicalResourceId.of(
					f"PulseCertificateValidation-{self.env_name}",
				),
			),
			on_update=cr.AwsSdkCall(
				service="ACM",
				action="describeCertificate",
				parameters={"CertificateArn": certificate.ref},
				physical_resource_id=cr.PhysicalResourceId.of(
					f"PulseCertificateValidation-{self.env_name}",
				),
			),
			policy=cr.AwsCustomResourcePolicy.from_statements(
				[
					iam.PolicyStatement(
						actions=["acm:DescribeCertificate"],
						resources=[certificate.ref],
					),
				],
			),
		)
		custom.node.add_dependency(certificate)
		return custom.get_response_field("Certificate.DomainValidationOptions")
