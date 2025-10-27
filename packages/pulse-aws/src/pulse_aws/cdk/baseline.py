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
from constructs import Construct


class BaselineStack(Stack):
	"""Infrastructure shared by every Pulse ECS deployment."""

	def __init__(
		self,
		scope: Construct,
		construct_id: str,
		*,
		deployment_name: str,
		certificate_arn: str,
		allowed_ingress_cidrs: Sequence[str] | None = None,
		**kwargs,
	) -> None:
		super().__init__(scope, construct_id, **kwargs)

		self.deployment_name = deployment_name
		self.allowed_ingress_cidrs = allowed_ingress_cidrs or ["0.0.0.0/0"]
		self.certificate_arn = certificate_arn

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
		for cidr in self.allowed_ingress_cidrs:
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
			load_balancer_name=f"{deployment_name}-alb",
		)

		acm_certificate = acm.Certificate.from_certificate_arn(
			self,
			"PulseCertificate",
			certificate_arn,
		)

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
			log_group_name=f"/aws/pulse/{deployment_name}/app",
			retention=logs.RetentionDays.THREE_MONTHS,
			removal_policy=RemovalPolicy.RETAIN,
		)

		self.repository = ecr.Repository(
			self,
			"PulseEcrRepository",
			repository_name=f"{deployment_name}",
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
			assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),  # pyright: ignore[reportArgumentType]
			description="Task role for Pulse ECS tasks",
		)

		self.cluster = ecs.Cluster(
			self,
			"PulseCluster",
			vpc=self.vpc,
			cluster_name=f"{deployment_name}",
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
			export_name=f"{self.deployment_name}-alb-dns",
		)
		CfnOutput(
			self,
			"AlbHostedZoneId",
			value=self.load_balancer.load_balancer_canonical_hosted_zone_id,
			export_name=f"{self.deployment_name}-alb-zone",
		)
		CfnOutput(
			self,
			"ListenerArn",
			value=self.listener.listener_arn,
			export_name=f"{self.deployment_name}-listener-arn",
		)
		CfnOutput(
			self,
			"PrivateSubnets",
			value=private_subnet_ids,
			export_name=f"{self.deployment_name}-private-subnets",
		)
		CfnOutput(
			self,
			"PublicSubnets",
			value=public_subnet_ids,
			export_name=f"{self.deployment_name}-public-subnets",
		)
		CfnOutput(
			self,
			"AlbSecurityGroupId",
			value=self.alb_security_group.security_group_id,
			export_name=f"{self.deployment_name}-alb-sg",
		)
		CfnOutput(
			self,
			"ServiceSecurityGroupId",
			value=self.service_security_group.security_group_id,
			export_name=f"{self.deployment_name}-service-sg",
		)
		CfnOutput(
			self,
			"ClusterName",
			value=self.cluster.cluster_name,
			export_name=f"{self.deployment_name}-cluster",
		)
		CfnOutput(
			self,
			"LogGroupName",
			value=self.log_group.log_group_name,
			export_name=f"{self.deployment_name}-log-group",
		)
		CfnOutput(
			self,
			"EcrRepositoryUri",
			value=self.repository.repository_uri,
			export_name=f"{self.deployment_name}-ecr",
		)
		CfnOutput(
			self,
			"VpcId",
			value=self.vpc.vpc_id,
			export_name=f"{self.deployment_name}-vpc",
		)
		CfnOutput(
			self,
			"CertificateArn",
			value=Token.as_string(self.certificate_arn),
			export_name=f"{self.deployment_name}-certificate-arn",
		)
		CfnOutput(
			self,
			"ExecutionRoleArn",
			value=self.execution_role.role_arn,
			export_name=f"{self.deployment_name}-execution-role-arn",
		)
		CfnOutput(
			self,
			"TaskRoleArn",
			value=self.task_role.role_arn,
			export_name=f"{self.deployment_name}-task-role-arn",
		)
