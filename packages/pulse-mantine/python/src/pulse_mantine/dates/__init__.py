import pulse as ps

from pulse_mantine.version import __version__

ps.require(
	{
		"pulse-mantine": __version__,
		"@mantine/dates": ">=8.0.0",
	}
)

ps.Import("@mantine/dates/styles.css", side_effect=True)
