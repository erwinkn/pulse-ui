#!/usr/bin/env python3
from __future__ import annotations

import os

import aws_cdk as cdk

from pulse_aws.cdk.baseline import BaselineStack
from pulse_aws.cdk.helpers import cvalue, lst

app = cdk.App()
deployment_name = cvalue(app, "deployment_name")
certificate_arn = cvalue(app, "certificate_arn")
allowed_cidrs = lst(cvalue(app, "allowed_ingress_cidrs", optional=True))

# Reaper configuration (with defaults)
reaper_schedule_minutes = int(
	cvalue(app, "reaper_schedule_minutes", optional=True) or "1"
)
reaper_max_age_hours = float(
	cvalue(app, "reaper_max_age_hours", optional=True) or "1.0"
)
reaper_deployment_timeout = float(
	cvalue(app, "reaper_deployment_timeout", optional=True) or "1.0"
)

BaselineStack(
	app,
	f"{deployment_name}-baseline",
	env=cdk.Environment(
		account=os.getenv("CDK_DEFAULT_ACCOUNT"),
		region=os.getenv("CDK_DEFAULT_REGION"),
	),
	deployment_name=deployment_name,
	certificate_arn=certificate_arn,
	allowed_ingress_cidrs=allowed_cidrs,
	reaper_schedule_minutes=reaper_schedule_minutes,
	reaper_max_age_hours=reaper_max_age_hours,
	reaper_deployment_timeout=reaper_deployment_timeout,
)

app.synth()
