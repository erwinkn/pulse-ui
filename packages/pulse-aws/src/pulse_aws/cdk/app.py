#!/usr/bin/env python3
from __future__ import annotations

import os

import aws_cdk as cdk

from pulse_aws.cdk.baseline import BaselineStack
from pulse_aws.cdk.helpers import cvalue, lst

app = cdk.App()
env_name = cvalue(app, "env")
certificate_arn = cvalue(app, "certificate_arn", optional=True)
domains = lst(cvalue(app, "domains", optional=True))
allowed_cidrs = lst(cvalue(app, "allowed_ingress_cidrs", optional=True))

BaselineStack(
	app,
	f"pulse-{env_name}-baseline",
	env=cdk.Environment(
		account=os.getenv("CDK_DEFAULT_ACCOUNT"),
		region=os.getenv("CDK_DEFAULT_REGION"),
	),
	env_name=env_name,
	certificate_arn=certificate_arn,
	domains=domains,
	allowed_ingress_cidrs=allowed_cidrs,
)

app.synth()
