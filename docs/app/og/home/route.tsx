import { ImageResponse } from "@takumi-rs/image-response";
import { getFaviconDataUrl, getPulseMarineColors, ogPalette } from "@/lib/og";

export const revalidate = false;

const { color: pulseMarineColor, glow: pulseMarineGlow } = getPulseMarineColors();
const faviconDataUrl = getFaviconDataUrl();

export async function GET() {
	const codeFontSize = 16;
	const codeLineHeight = 24;
	const codeColors = {
		keyword: pulseMarineColor,
		decorator: "rgba(196, 181, 253, 0.95)",
		type: "rgba(94, 234, 212, 0.95)",
		number: "rgba(251, 191, 36, 0.95)",
		function: "rgba(248, 250, 252, 0.95)",
	};
	const codeLines = [
		{
			key: "import",
			tokens: [
				{ key: "kw-import", text: "import", color: codeColors.keyword },
				{ key: "import-rest", text: " pulse as ps" },
			],
		},
		{ key: "blank-1", blank: true },
		{
			key: "class",
			tokens: [
				{ key: "kw-class", text: "class ", color: codeColors.keyword },
				{ key: "class-name", text: "Counter", color: codeColors.type },
				{ key: "class-open", text: "(" },
				{ key: "class-base", text: "ps.State", color: codeColors.type },
				{ key: "class-close", text: "):" },
			],
		},
		{
			key: "count",
			tokens: [
				{ key: "count-label", text: "count: " },
				{ key: "count-type", text: "int", color: codeColors.type },
				{ key: "count-equals", text: " = " },
				{ key: "count-value", text: "0", color: codeColors.number },
			],
			indent: 24,
		},
		{ key: "blank-2", blank: true },
		{
			key: "decorator",
			tokens: [
				{ key: "decorator-ps-component", text: "@ps.component", color: codeColors.decorator },
			],
		},
		{
			key: "def",
			tokens: [
				{ key: "kw-def", text: "def ", color: codeColors.keyword },
				{ key: "def-name", text: "App", color: codeColors.function },
				{ key: "def-sig", text: "():" },
			],
		},
		{
			key: "with-init",
			tokens: [
				{ key: "kw-with", text: "with ", color: codeColors.keyword },
				{ key: "with-call", text: "ps.init", color: codeColors.function },
				{ key: "with-sig", text: "():" },
			],
			indent: 24,
		},
		{
			key: "state",
			tokens: [
				{ key: "state-label", text: "state = " },
				{ key: "state-class", text: "Counter", color: codeColors.type },
				{ key: "state-call", text: "()" },
			],
			indent: 48,
		},
		{
			key: "return",
			tokens: [
				{ key: "kw-return", text: "return ", color: codeColors.keyword },
				{ key: "return-call", text: "ps.div(...)", color: codeColors.function },
			],
			indent: 24,
		},
	];

	return new ImageResponse(
		<div
			style={{
				width: "100%",
				height: "100%",
				display: "flex",
				flexDirection: "row",
				alignItems: "center",
				justifyContent: "space-between",
				gap: "36px",
				padding: "64px",
				color: "white",
				backgroundColor: ogPalette.homeBackground,
				backgroundImage: `radial-gradient(circle at 15% 10%, ${pulseMarineGlow}, transparent 55%), radial-gradient(circle at 85% 0%, rgba(255, 255, 255, 0.08), transparent 60%)`,
			}}
		>
			<div style={{ display: "flex", flexDirection: "column", gap: "28px", maxWidth: 620 }}>
				<div style={{ display: "flex", alignItems: "center", gap: "14px" }}>
					{/* biome-ignore lint/performance/noImgElement: data URL required for ImageResponse. */}
					<img src={faviconDataUrl} width={36} height={36} alt="" />
					<span
						style={{
							fontSize: 26,
							fontWeight: 700,
							letterSpacing: "-0.02em",
							opacity: 0.9,
						}}
					>
						Pulse
					</span>
				</div>
				<span
					style={{
						fontSize: 64,
						fontWeight: 700,
						lineHeight: 1.05,
						letterSpacing: "-0.04em",
					}}
				>
					Reactive web apps. Pure Python.
				</span>
				<span
					style={{
						fontSize: 28,
						lineHeight: 1.4,
						color: "rgba(255, 255, 255, 0.72)",
					}}
				>
					Build interactive web apps entirely in Python. Pulse renders your code to a React frontend
					and keeps it in sync over WebSocket.
				</span>
				<div style={{ display: "flex", gap: "14px" }}>
					<div
						style={{
							padding: "12px 22px",
							borderRadius: 999,
							backgroundColor: "white",
							color: "#0b0f14",
							fontSize: 18,
							fontWeight: 600,
						}}
					>
						Get started
					</div>
					<div
						style={{
							padding: "12px 22px",
							borderRadius: 999,
							border: "1px solid rgba(255, 255, 255, 0.25)",
							color: "white",
							fontSize: 18,
							fontWeight: 600,
						}}
					>
						Docs
					</div>
				</div>
			</div>

			<div
				style={{
					display: "flex",
					flexDirection: "column",
					gap: "14px",
					width: 420,
					minHeight: 300,
					padding: "22px 26px",
					borderRadius: 18,
					backgroundColor: ogPalette.homePanel,
					border: "1px solid rgba(255, 255, 255, 0.12)",
					boxShadow: `0 18px 40px rgba(0, 0, 0, 0.45)`,
				}}
			>
				<div
					style={{
						fontFamily: "monospace",
						fontSize: codeFontSize,
						lineHeight: `${codeLineHeight}px`,
						color: "rgba(255, 255, 255, 0.84)",
						display: "flex",
						flexDirection: "column",
						whiteSpace: "pre",
					}}
				>
					{codeLines.map((line) =>
						line.blank ? (
							<div key={line.key} style={{ height: codeLineHeight }} />
						) : (
							<div
								key={line.key}
								style={{
									display: "flex",
									paddingLeft: line.indent ?? 0,
								}}
							>
								{line.tokens?.map((token) => (
									<span key={token.key} style={token.color ? { color: token.color } : undefined}>
										{token.text}
									</span>
								))}
							</div>
						),
					)}
				</div>
			</div>
		</div>,
		{
			width: 1200,
			height: 630,
			format: "webp",
		},
	);
}
