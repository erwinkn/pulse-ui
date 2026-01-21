import { ImageResponse } from "@takumi-rs/image-response";
import { notFound } from "next/navigation";
import { getFaviconDataUrl, getPulseMarineColors } from "@/lib/og";
import { getPageImage, source } from "@/lib/source";

export const revalidate = false;

const { color: pulseMarineColor, glow: pulseMarineGlow } = getPulseMarineColors();
const faviconDataUrl = getFaviconDataUrl();
export async function GET(_req: Request, { params }: RouteContext<"/og/docs/[...slug]">) {
	const { slug } = await params;
	const page = source.getPage(slug.slice(0, -1));
	if (!page) notFound();

	return new ImageResponse(
		<div
			style={{
				width: "100%",
				height: "100%",
				backgroundColor: "#050505",
				position: "relative",
				display: "flex",
				flexDirection: "column",
				overflow: "hidden",
				color: "white",
				backgroundImage: `linear-gradient(to bottom right, ${pulseMarineGlow}, transparent)`,
			}}
		>
			<div
				style={{
					display: "flex",
					flexDirection: "column",
					width: "100%",
					height: "100%",
					padding: "60px",
					position: "relative",
					justifyContent: "space-between",
				}}
			>
				<div
					style={{
						display: "flex",
						flexDirection: "column",
						gap: "32px",
						marginBottom: "40px",
						textWrap: "pretty",
					}}
				>
					<span
						style={{
							fontSize: 72,
							fontWeight: 800,
							lineHeight: 1.1,
							letterSpacing: "-0.04em",
							color: "white",
						}}
					>
						{page.data.title}
					</span>
					{page.data.description ? (
						<span
							style={{
								fontSize: 44,
								color: "#a1a1aa",
								fontWeight: 400,
								lineHeight: 1.4,
								maxWidth: "95%",
								letterSpacing: "-0.01em",
								lineClamp: 2,
								textOverflow: "ellipsis",
								overflow: "hidden",
							}}
						>
							{page.data.description}
						</span>
					) : null}
				</div>

				<div
					style={{
						display: "flex",
						alignItems: "center",
						gap: "28px",
					}}
				>
					{/* biome-ignore lint/performance/noImgElement: data URL required for ImageResponse. */}
					<img src={faviconDataUrl} width={44} height={44} alt="" />
					<span
						style={{
							fontSize: 32,
							fontWeight: 700,
							letterSpacing: "-0.02em",
							color: "white",
							opacity: 0.9,
						}}
					>
						Pulse
					</span>
					<div style={{ flexGrow: 1 }} />
					<div
						style={{
							height: 4,
							width: 60,
							backgroundColor: pulseMarineGlow,
							borderRadius: 2,
						}}
					/>
					<span
						style={{
							fontSize: 22,
							fontWeight: 700,
							textTransform: "uppercase",
							letterSpacing: "0.2em",
							color: pulseMarineColor,
							opacity: 0.8,
						}}
					>
						Documentation
					</span>
				</div>
			</div>
		</div>,
		{
			width: 1200,
			height: 630,
			format: "png",
		},
	);
}

export function generateStaticParams() {
	return source.getPages().map((page) => ({
		lang: page.locale,
		slug: getPageImage(page).segments,
	}));
}
