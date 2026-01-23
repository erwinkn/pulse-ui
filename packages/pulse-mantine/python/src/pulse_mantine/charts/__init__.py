import pulse as ps

from pulse_mantine.version import __version__

ps.require(
	{
		"pulse-mantine": __version__,
		"@mantine/charts": ">=8.0.0",
	}
)

ps.Import("@mantine/charts/styles.css", side_effect=True)
