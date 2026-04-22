from __future__ import annotations

from pulse_railway.commands.deploy.common import ResolvedDeployCommand
from pulse_railway.deployment import DeployResult, deploy


async def run_deploy_image(command: ResolvedDeployCommand) -> DeployResult:
	return await deploy(
		project=command.project,
		docker=command.docker,
		deployment_name=command.deployment_name,
		deployment_id=command.deployment_id,
		app_file=command.app_file,
		web_root=command.web_root,
	)
