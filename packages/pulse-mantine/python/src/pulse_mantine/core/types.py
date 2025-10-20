from typing import Literal, Any

MantineFontFamily = Literal["monospace", "text", "heading"]
MantineTextAlign = Literal["left", "right", "center", "justify"]
MantineFontStyle = Literal["normal", "italic", "oblique"]
MantineTextTransform = Literal[
	"none",
	"capitalize",
	"uppercase",
	"lowercase",
	"full-width",
	"full-size-kana",
]
MantineTextDecoration = Literal["none", "underline", "overline", "line-through"]
MantinePosition = Literal["static", "relative", "absolute", "fixed", "sticky"]

DefaultMantineColor = (
	Literal[
		"dark",
		"gray",
		"red",
		"pink",
		"grape",
		"violet",
		"indigo",
		"blue",
		"cyan",
		"green",
		"lime",
		"yellow",
		"orange",
		"teal",
	]
	| str
)
MantineColor = str | DefaultMantineColor
MantineColorShade = Literal[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
MantineColorScheme = Literal["light", "dark", "auto"]

DefaultMantineSize = Literal["xs", "sm", "md", "lg", "xl"]
MantineSize = str | DefaultMantineSize

MantineBreakpoint = str | DefaultMantineSize
MantineBreakpointsValues = dict[MantineBreakpoint, str]
MantineFontSize = str  #
MantineFontSizesValues = dict[str, str]


MantineTextWrap = Literal["wrap", "nowrap", "balance", "pretty", "stable"]
