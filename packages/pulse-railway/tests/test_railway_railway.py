from __future__ import annotations

import pytest
from pulse_railway.railway import RailwayGraphQLClient


@pytest.mark.asyncio
async def test_update_service_instance_includes_cron_schedule(monkeypatch) -> None:
	calls: list[tuple[str, dict[str, object] | None]] = []

	async def fake_graphql(
		self: RailwayGraphQLClient,
		query: str,
		variables: dict[str, object] | None = None,
	) -> object:
		calls.append((query, variables))
		return {}

	monkeypatch.setattr(RailwayGraphQLClient, "graphql", fake_graphql)
	client = RailwayGraphQLClient(token="token")
	try:
		await client.update_service_instance(
			service_id="svc-1",
			environment_id="env",
			source_image="image:latest",
			num_replicas=1,
			start_command="pulse-railway janitor run",
			cron_schedule="*/5 * * * *",
			restart_policy_type="NEVER",
		)
	finally:
		await client.aclose()

	assert len(calls) == 1
	query, variables = calls[0]
	assert "serviceInstanceUpdate" in query
	assert variables is not None
	assert variables["serviceId"] == "svc-1"
	assert variables["environmentId"] == "env"
	assert variables["input"] == {
		"source": {"image": "image:latest"},
		"numReplicas": 1,
		"startCommand": "pulse-railway janitor run",
		"cronSchedule": "*/5 * * * *",
		"restartPolicyType": "NEVER",
	}
