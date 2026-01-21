import pulse as ps

from pulse_mantine.version import __version__

ps.require(
	{
		"pulse-mantine": __version__,
		"@mantine/form": ">=8.0.0",
	}
)
