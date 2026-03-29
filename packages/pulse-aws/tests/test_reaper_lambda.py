from __future__ import annotations

from datetime import datetime, timezone

import pulse_aws.reaper_lambda as reaper_lambda
import pytest
from pulse_aws.constants import AFFINITY_QUERY_PARAM
from pulse_aws.reaper_lambda import (
	cleanup_inactive_services,
	cleanup_stuck_deploying_services,
	get_listener_rules_map,
	process_draining_services,
)


class FakeElbv2Client:
	def __init__(self, *, actions: list[dict[str, object]] | None = None) -> None:
		self.modify_rule_calls: list[dict[str, object]] = []
		self.delete_rule_calls: list[dict[str, object]] = []
		self.delete_target_group_calls: list[dict[str, object]] = []
		self.actions = actions or [{"TargetGroupArn": "arn:target-group"}]

	def describe_rules(self, *, ListenerArn: str):
		assert ListenerArn == "arn:listener"
		return {
			"Rules": [
				{
					"Priority": "default",
					"RuleArn": "arn:default",
					"Conditions": [],
					"Actions": [],
				},
				{
					"Priority": "140",
					"RuleArn": "arn:header",
					"Conditions": [
						{
							"Field": "query-string",
							"QueryStringConfig": {
								"Values": [
									{
										"Key": AFFINITY_QUERY_PARAM,
										"Value": "test-20260306-151500Z",
									}
								],
							},
						}
					],
					"Actions": self.actions,
				},
			]
		}

	def modify_rule(self, **kwargs: object) -> None:
		self.modify_rule_calls.append(kwargs)

	def delete_rule(self, **kwargs: object) -> None:
		self.delete_rule_calls.append(kwargs)

	def delete_target_group(self, **kwargs: object) -> None:
		self.delete_target_group_calls.append(kwargs)


class FakePaginator:
	def __init__(self, service_arns: list[str]) -> None:
		self.service_arns = service_arns

	def paginate(self, *, cluster: str):
		assert cluster == "test"
		yield {"serviceArns": self.service_arns}


class FakeEcsClient:
	def __init__(
		self,
		*,
		service: dict[str, object],
		tag_state: str = "draining",
		task_arns: list[str] | None = None,
	) -> None:
		self.service = service
		self.tag_state = tag_state
		self.task_arns = task_arns or []
		self.update_service_calls: list[dict[str, object]] = []
		self.delete_service_calls: list[dict[str, object]] = []

	def get_paginator(self, name: str) -> FakePaginator:
		assert name == "list_services"
		return FakePaginator([str(self.service["serviceArn"])])

	def describe_services(
		self, *, cluster: str, services: list[str]
	) -> dict[str, list[dict[str, object]]]:
		assert cluster == "test"
		assert services == [self.service["serviceArn"]]
		return {"services": [self.service]}

	def list_tags_for_resource(
		self, *, resourceArn: str
	) -> dict[str, list[dict[str, str]]]:
		assert resourceArn == self.service["serviceArn"]
		return {
			"tags": [
				{"key": "state", "value": self.tag_state},
				{"key": "deployment_id", "value": str(self.service["serviceName"])},
			]
		}

	def list_tasks(self, *, cluster: str, serviceName: str) -> dict[str, list[str]]:
		assert cluster == "test"
		assert serviceName == self.service["serviceName"]
		return {"taskArns": self.task_arns}

	def describe_tasks(
		self, *, cluster: str, tasks: list[str]
	) -> dict[str, list[dict[str, str]]]:
		assert cluster == "test"
		assert tasks == self.task_arns
		return {"tasks": [{"taskArn": task_arn} for task_arn in tasks]}

	def update_service(self, **kwargs: object) -> None:
		self.update_service_calls.append(kwargs)

	def delete_service(self, **kwargs: object) -> None:
		self.delete_service_calls.append(kwargs)


class FakeSsmExceptions:
	class ParameterNotFound(Exception):
		pass


class FakeSsmClient:
	exceptions = FakeSsmExceptions

	def __init__(self, values: dict[str, str] | None = None) -> None:
		self.values = values or {}

	def get_parameter(self, *, Name: str) -> dict[str, dict[str, str]]:
		if Name not in self.values:
			raise self.exceptions.ParameterNotFound()
		return {"Parameter": {"Value": self.values[Name]}}

	def delete_parameter(self, *, Name: str) -> None:
		self.values.pop(Name, None)

	def get_paginator(self, name: str):
		assert name == "get_parameters_by_path"

		class EmptyParametersPaginator:
			def paginate(self, *, Path: str, Recursive: bool):
				assert Recursive is False
				yield {"Parameters": []}

		return EmptyParametersPaginator()


def make_service(
	*,
	deployment_id: str,
	running_count: int,
	desired_count: int,
	status: str = "ACTIVE",
) -> dict[str, object]:
	return {
		"serviceArn": f"arn:service/{deployment_id}",
		"serviceName": deployment_id,
		"status": status,
		"runningCount": running_count,
		"desiredCount": desired_count,
		"createdAt": datetime.now(timezone.utc),
		"loadBalancers": [
			{
				"targetGroupArn": f"arn:target-group/{deployment_id}",
				"containerPort": 8000,
			}
		],
	}


def test_get_listener_rules_map_collects_query_rules():
	rules_map = get_listener_rules_map(FakeElbv2Client(), "arn:listener")

	assert rules_map == {
		"test-20260306-151500Z": {
			"rule_arn": "arn:header",
			"target_group_arn": "arn:target-group",
		}
	}


def test_process_draining_services_replaces_affinity_rule_with_404_before_scale_down(
	monkeypatch: pytest.MonkeyPatch,
):
	deployment_id = "test-20260306-151500Z"
	monkeypatch.setattr(reaper_lambda, "DEPLOYMENT_NAME", "test")
	service = make_service(
		deployment_id=deployment_id,
		running_count=2,
		desired_count=2,
	)
	task_ids = ["task-1", "task-2"]
	task_arns = [f"arn:task/{task_id}" for task_id in task_ids]
	ecs = FakeEcsClient(service=service, task_arns=task_arns)
	elbv2 = FakeElbv2Client()
	ssm = FakeSsmClient(
		{
			f"/apps/test/{deployment_id}/tasks/{task_id}": "draining"
			for task_id in task_ids
		}
	)

	drained = process_draining_services(
		cluster="test",
		listener_arn="arn:listener",
		ecs=ecs,
		elbv2=elbv2,
		ssm_client=ssm,
		max_age_hr=1.0,
	)

	assert drained == 1
	assert elbv2.modify_rule_calls == [
		{
			"RuleArn": "arn:header",
			"Actions": [
				{
					"Type": "fixed-response",
					"FixedResponseConfig": {
						"StatusCode": "404",
						"ContentType": "text/plain",
						"MessageBody": f"Deployment {deployment_id} is no longer available.",
					},
				}
			],
		}
	]
	assert ecs.update_service_calls == [
		{
			"cluster": "test",
			"service": f"arn:service/{deployment_id}",
			"desiredCount": 0,
		}
	]


def test_process_draining_services_waits_for_tasks_that_are_not_ready(
	monkeypatch: pytest.MonkeyPatch,
):
	deployment_id = "test-20260306-151500Z"
	monkeypatch.setattr(reaper_lambda, "DEPLOYMENT_NAME", "test")
	service = make_service(
		deployment_id=deployment_id,
		running_count=2,
		desired_count=2,
	)
	task_ids = ["task-1", "task-2"]
	task_arns = [f"arn:task/{task_id}" for task_id in task_ids]
	ecs = FakeEcsClient(service=service, task_arns=task_arns)
	elbv2 = FakeElbv2Client()
	ssm = FakeSsmClient(
		{
			f"/apps/test/{deployment_id}/tasks/task-1": "draining",
			f"/apps/test/{deployment_id}/tasks/task-2": "healthy",
		}
	)

	drained = process_draining_services(
		cluster="test",
		listener_arn="arn:listener",
		ecs=ecs,
		elbv2=elbv2,
		ssm_client=ssm,
		max_age_hr=1.0,
	)

	assert drained == 0
	assert elbv2.modify_rule_calls == []
	assert ecs.update_service_calls == []


def test_cleanup_inactive_services_deletes_target_group_after_rule_becomes_fixed_404():
	deployment_id = "test-20260306-151500Z"
	service = make_service(
		deployment_id=deployment_id,
		running_count=0,
		desired_count=0,
	)
	ecs = FakeEcsClient(service=service)
	elbv2 = FakeElbv2Client(
		actions=[
			{
				"Type": "fixed-response",
				"FixedResponseConfig": {"StatusCode": "404"},
			}
		]
	)
	ssm = FakeSsmClient()

	cleaned = cleanup_inactive_services(
		cluster="test",
		listener_arn="arn:listener",
		ecs=ecs,
		elbv2=elbv2,
		ssm_client=ssm,
	)

	assert cleaned == 1
	assert elbv2.delete_rule_calls == [{"RuleArn": "arn:header"}]
	assert elbv2.delete_target_group_calls == [
		{"TargetGroupArn": f"arn:target-group/{deployment_id}"}
	]
	assert ecs.delete_service_calls == [
		{
			"cluster": "test",
			"service": f"arn:service/{deployment_id}",
			"force": True,
		}
	]


def test_cleanup_stuck_deploying_services_uses_service_target_group_fallback(
	monkeypatch: pytest.MonkeyPatch,
):
	deployment_id = "test-20260306-151500Z"
	monkeypatch.setattr(reaper_lambda, "DEPLOYMENT_NAME", "test")
	service = make_service(
		deployment_id=deployment_id,
		running_count=1,
		desired_count=1,
	)
	service["createdAt"] = datetime.now(timezone.utc).replace(year=2024)
	ecs = FakeEcsClient(service=service, tag_state="deploying")
	elbv2 = FakeElbv2Client(
		actions=[
			{
				"Type": "fixed-response",
				"FixedResponseConfig": {"StatusCode": "404"},
			}
		]
	)
	ssm = FakeSsmClient()

	cleaned = cleanup_stuck_deploying_services(
		cluster="test",
		listener_arn="arn:listener",
		max_age_hr=0,
		ecs=ecs,
		elbv2=elbv2,
		ssm_client=ssm,
	)

	assert cleaned == 1
	assert elbv2.delete_rule_calls == [{"RuleArn": "arn:header"}]
	assert elbv2.delete_target_group_calls == [
		{"TargetGroupArn": f"arn:target-group/{deployment_id}"}
	]
	assert ecs.update_service_calls == [
		{
			"cluster": "test",
			"service": f"arn:service/{deployment_id}",
			"desiredCount": 0,
		}
	]
	assert ecs.delete_service_calls == [
		{
			"cluster": "test",
			"service": f"arn:service/{deployment_id}",
			"force": True,
		}
	]


def test_cleanup_inactive_services_also_cleans_drain_state_services():
	deployment_id = "test-20260306-151500Z"
	service = make_service(
		deployment_id=deployment_id,
		running_count=0,
		desired_count=0,
		status="DRAINING",
	)
	ecs = FakeEcsClient(service=service)
	elbv2 = FakeElbv2Client(
		actions=[
			{
				"Type": "fixed-response",
				"FixedResponseConfig": {"StatusCode": "404"},
			}
		]
	)
	ssm = FakeSsmClient()

	cleaned = cleanup_inactive_services(
		cluster="test",
		listener_arn="arn:listener",
		ecs=ecs,
		elbv2=elbv2,
		ssm_client=ssm,
	)

	assert cleaned == 1
	assert ecs.delete_service_calls == [
		{
			"cluster": "test",
			"service": f"arn:service/{deployment_id}",
			"force": True,
		}
	]
