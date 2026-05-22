from __future__ import annotations

import argparse
import json

import pytest
from pulse_railway.cli import _run_control
from pulse_railway.control import (
	DrainingDeployment,
	promote_deployment,
	register_deployment,
)
from pulse_railway.store import ActiveDeploymentError, MemoryDeploymentStore


@pytest.mark.asyncio
async def test_control_registers_pending_deployment() -> None:
	store = MemoryDeploymentStore()
	await store.set_active(deployment_id="prod-current", service_name="pulse-current")

	await register_deployment(
		store,
		deployment_id="prod-new",
		service_name="pulse-prod-new",
	)

	assert await store.get_active_deployment() == "prod-current"
	deployment = await store.get_deployment("prod-new")
	assert deployment is not None
	assert deployment.state == "pending"
	assert deployment.service_name == "pulse-prod-new"


@pytest.mark.asyncio
async def test_control_rejects_registering_active_deployment() -> None:
	store = MemoryDeploymentStore()
	await store.set_active(deployment_id="prod-current", service_name="pulse-current")

	with pytest.raises(ActiveDeploymentError):
		await register_deployment(
			store,
			deployment_id="prod-current",
			service_name="pulse-current",
		)

	assert await store.get_active_deployment() == "prod-current"


@pytest.mark.asyncio
async def test_control_promotes_and_marks_draining_deployments() -> None:
	store = MemoryDeploymentStore()
	await store.set_active(deployment_id="prod-stale", service_name="pulse-stale")

	await promote_deployment(
		store,
		active_deployment_id="prod-new",
		active_service_name="pulse-prod-new",
		draining=[
			DrainingDeployment(
				deployment_id="prod-old",
				service_name="pulse-prod-old",
				drain_started_at=123.0,
			)
		],
	)

	assert await store.get_active_deployment() == "prod-new"
	explicit_draining = await store.get_deployment("prod-old")
	assert explicit_draining is not None
	assert explicit_draining.state == "draining"
	assert explicit_draining.service_name == "pulse-prod-old"
	assert explicit_draining.drain_started_at == 123.0
	stale = await store.get_deployment("prod-stale")
	assert stale is not None
	assert stale.state == "draining"
	assert stale.service_name == "pulse-stale"
	assert stale.drain_started_at is not None


@pytest.mark.asyncio
async def test_control_cli_promotes_inside_railway_runtime(
	monkeypatch: pytest.MonkeyPatch,
	capsys: pytest.CaptureFixture[str],
) -> None:
	store = MemoryDeploymentStore()
	await store.set_active(deployment_id="prod-old", service_name="pulse-prod-old")
	monkeypatch.setenv("RAILWAY_SERVICE_ID", "router")
	monkeypatch.setattr("pulse_railway.cli.deployment_store_from_env", lambda: store)

	result = await _run_control(
		argparse.Namespace(
			control_command="promote",
			active_deployment_id="prod-new",
			active_service_name="pulse-prod-new",
			draining_json=json.dumps(
				[
					{
						"deployment_id": "prod-old",
						"service_name": "pulse-prod-old",
						"drain_started_at": 123.0,
					}
				]
			),
		)
	)

	assert result == 0
	assert json.loads(capsys.readouterr().out) == {"ok": True}
	assert await store.get_active_deployment() == "prod-new"
