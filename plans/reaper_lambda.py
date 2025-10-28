"""
ECS Draining Reaper Lambda
Polls draining services and retires them when all tasks report ShutdownReady==1
"""

import datetime as dt
import os

import boto3

ecs = boto3.client("ecs")
elb = boto3.client("elbv2")
cw = boto3.client("cloudwatch")

CLUSTER = os.environ["CLUSTER"]
DEPLOYMENT_NAME = os.environ["DEPLOYMENT_NAME"]
CONSEC = int(os.environ.get("CONSEC", "3"))
PERIOD = int(os.environ.get("PERIOD", "300"))
MIN_AGE_SEC = int(os.environ.get("MIN_AGE_SEC", "120"))
MAX_AGE_HR = int(os.environ.get("MAX_AGE_HR", "48"))


def _svc_tags(arn):
	try:
		t = ecs.list_tags_for_resource(resourceArn=arn).get("tags", [])
		return {d["key"]: d["value"] for d in t}
	except Exception:
		return {}


def _get_task_ids(service_name):
	"""List all running tasks for this service"""
	task_arns = ecs.list_tasks(
		cluster=CLUSTER, serviceName=service_name, desiredStatus="RUNNING"
	).get("taskArns", [])
	if not task_arns:
		return []
	tasks = ecs.describe_tasks(cluster=CLUSTER, tasks=task_arns)["tasks"]
	return [t["taskArn"].split("/")[-1] for t in tasks]


def _shutdown_ready(deployment_id, task_ids):
	"""Check if ALL tasks report ShutdownReady==1 for CONSEC periods"""
	if not task_ids:
		return True  # no tasks = ready

	end = dt.datetime.now(dt.timezone.utc)
	start = end - dt.timedelta(seconds=PERIOD * CONSEC + 60)

	# Build queries for each task
	queries = []
	for i, tid in enumerate(task_ids):
		queries.append(
			{
				"Id": f"m{i}",
				"MetricStat": {
					"Metric": {
						"Namespace": "App/Drain",
						"MetricName": "ShutdownReady",
						"Dimensions": [
							{"Name": "deployment_name", "Value": DEPLOYMENT_NAME},
							{"Name": "deployment_id", "Value": deployment_id},
							{"Name": "task_id", "Value": tid},
						],
					},
					"Period": PERIOD,
					"Stat": "Average",
				},
				"ReturnData": True,
			}
		)

	if not queries:
		return True

	resp = cw.get_metric_data(
		MetricDataQueries=queries[:500], StartTime=start, EndTime=end
	)  # CW limit 500

	# ALL tasks must have values and all must be 1 for last CONSEC periods
	for r in resp["MetricDataResults"]:
		vals = r.get("Values", [])
		if len(vals) < 1 or not all(v >= 0.99 for v in vals[-CONSEC:]):
			return False
	return True


def _svc_age_ok(svc):
	created = svc.get("createdAt")
	if not created:
		return True
	age = (dt.datetime.now(dt.timezone.utc) - created).total_seconds()
	return age >= MIN_AGE_SEC


def _svc_too_old(svc):
	created = svc.get("createdAt")
	if not created:
		return False
	age_hr = (dt.datetime.now(dt.timezone.utc) - created).total_seconds() / 3600.0
	return age_hr >= MAX_AGE_HR


def _find_tg_arn(svc):
	lbs = svc.get("loadBalancers", [])
	return lbs[0]["targetGroupArn"] if lbs else None


def _remove_listener_refs(tg_arn):
	lbs = elb.describe_listeners(
		LoadBalancerArn=elb.describe_target_groups(TargetGroupArns=[tg_arn])[
			"TargetGroups"
		][0]["LoadBalancerArns"][0]
	)["Listeners"]
	for listener in lbs:
		# default action or rules; we only handle rules to be safe
		rules = elb.describe_rules(ListenerArn=listener["ListenerArn"])["Rules"]
		for rule in rules:
			acts = rule.get("Actions", [])
			if any(a.get("TargetGroupArn") == tg_arn for a in acts):
				# Remove or modify—simplest: delete rule if it's not default
				if rule["IsDefault"]:
					# Replace default action to remove this TG if present
					new_acts = [a for a in acts if a.get("TargetGroupArn") != tg_arn]
					if new_acts:
						elb.modify_listener(
							ListenerArn=listener["ListenerArn"], DefaultActions=new_acts
						)
				else:
					elb.delete_rule(RuleArn=rule["RuleArn"])


def handler(event, context):
	arns = ecs.list_services(cluster=CLUSTER).get("serviceArns", [])
	services_to_cleanup = []  # Services with runningCount==0

	for i in range(0, len(arns), 10):
		svcs = ecs.describe_services(cluster=CLUSTER, services=arns[i : i + 10])[
			"services"
		]
		for svc in svcs:
			name = svc["serviceName"]

			# Track services with no running tasks for cleanup
			if svc.get("runningCount", 0) == 0:
				services_to_cleanup.append((name, svc))
				continue

			tags = _svc_tags(svc["serviceArn"])
			if tags.get("state") != "draining" or (
				tags.get("deployment_name") not in (DEPLOYMENT_NAME, None, "")
				and tags.get("deployment_name") != DEPLOYMENT_NAME
			):
				continue

			# Services are named svc-{deployment_name}-{deployment_id}
			if not name.startswith(f"svc-{DEPLOYMENT_NAME}-"):
				continue

			deployment_id = name.split(f"svc-{DEPLOYMENT_NAME}-", 1)[1]

			if not _svc_age_ok(svc):
				continue

			task_ids = _get_task_ids(name)
			if _shutdown_ready(deployment_id, task_ids) or _svc_too_old(svc):
				# Mark for draining by setting desiredCount=0
				if svc.get("desiredCount", 0) > 0:
					ecs.update_service(cluster=CLUSTER, service=name, desiredCount=0)
					print(f"Set {name} desiredCount=0 (will cleanup on next run)")
				# Don't wait - let the next invocation clean it up

	# Clean up all services with runningCount==0
	for name, svc in services_to_cleanup:
		tg_arn = _find_tg_arn(svc)

		if tg_arn:
			try:
				_remove_listener_refs(tg_arn)
			except Exception:
				pass
			try:
				elb.delete_target_group(TargetGroupArn=tg_arn)
			except Exception:
				pass

		try:
			ecs.delete_service(cluster=CLUSTER, service=name, force=True)
		except Exception:
			pass

		print(f"Cleaned up {name}")
