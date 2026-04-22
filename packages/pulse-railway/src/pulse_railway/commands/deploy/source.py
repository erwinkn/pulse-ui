from __future__ import annotations

from pulse_railway.commands.deploy.common import ResolvedDeployCommand
from pulse_railway.deployment import DeployUpResult, deploy_up


async def run_deploy_source(command: ResolvedDeployCommand) -> DeployUpResult:
	return await deploy_up(
		project=command.project,
		docker=command.docker,
		deployment_name=command.deployment_name,
		deployment_id=command.deployment_id,
		app_file=command.app_file,
		web_root=command.web_root,
		cli_token_env_name=command.cli_token_env_name,
		no_gitignore=command.no_gitignore,
	)
