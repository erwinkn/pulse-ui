import pulse as ps

from pulse_mantine.version import __version__

ps.require(
	{
		"pulse-mantine": __version__,
		"@mantine/core": ">=8.0.0",
		"@mantine/dropzone": ">=8.0.0",
		"@mantine/hooks": ">=8.0.0",
	}
)

ps.Import(
	"@mantine/core/styles.css",
	side_effect=True,
	before=["@mantine/dropzone/styles.css"],
)
ps.Import("@mantine/dropzone/styles.css", side_effect=True)
