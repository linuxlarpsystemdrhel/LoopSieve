"""Generate the original LoopSieve vector lockups and export PNGs via librsvg."""

import subprocess
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "assets" / "branding"
INK = "#142129"
CANVAS = "#F1F7F6"
TEAL = "#117B6E"
MUTED = "#516E73"
NIGHT = "#111D24"
PAPER = "#EFF8F7"
MINT = "#5CDECB"
FOG = "#A3BEC1"
RULE = "#C6DBD9"


def svg(width, height, label, body):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{label}">\n'
        f"<title>{label}</title>\n{body}\n</svg>\n"
    )


def mark(fg=INK, accent=TEAL, muted=MUTED):
    return f"""
    <g fill="none" stroke-linecap="round" stroke-linejoin="round" stroke-width="8">
      <path d="M12 27h12M9 44h10M12 61h9" stroke="{muted}"/>
      <path d="M68 28H48a20 20 0 1 0 0 40h10" stroke="{fg}"/>
      <path d="M57 68h4l19-19m-13 0h13v13" stroke="{accent}"/>
    </g>
    """


def wordmark(x, y, size, color):
    return (
        f'<text x="{x}" y="{y}" font-family="Liberation Sans, Arial, sans-serif" '
        f'font-size="{size}" font-weight="700" letter-spacing="-1.8" fill="{color}">LoopSieve</text>'
    )


def lockup(fg, accent, muted):
    body = f'<g transform="translate(12 8)">{mark(fg, accent, muted)}</g>'
    return svg(365, 112, "LoopSieve", body + wordmark(114, 73, 48, fg))


def wide(social):
    bg, fg, accent, muted, rule = (
        (NIGHT, PAPER, MINT, FOG, "#2F4951")
        if social
        else (CANVAS, INK, TEAL, MUTED, RULE)
    )
    height = 640 if social else 360
    offset = (height - 360) // 2
    body = f"""
      <rect width="1280" height="{height}" fill="{bg}"/>
      <g transform="translate(0 {offset})">
        <g transform="translate(83 69) scale(.8)">{mark(fg, accent, muted)}</g>
        {wordmark(79, 221, 84, fg)}
        <text x="84" y="274" font-family="Liberation Sans, Arial, sans-serif" font-size="27"
          fill="{muted}">Local verification for coding workflows</text>
        <path d="M715 60v241" stroke="{rule}" stroke-width="2"/>
        <g font-family="Liberation Mono, monospace" font-weight="700" font-size="16" letter-spacing="1.4" fill="{muted}">
          <text x="780" y="96">CHECK OUTPUT</text>
          <text x="1007" y="96">DIAGNOSTIC DELTA</text>
        </g>
        <g fill="none" stroke-linecap="round" stroke-width="10">
          <path d="M784 133h115m-115 29h76m-76 29h100m-100 29h53m-53 29h86m-86 29h70"
            stroke="{rule}"/>
          <path d="M784 191h100m-100 58h86" stroke="{muted}"/>
          <path d="M920 203h58m-14-14 14 14-14 14" stroke="{accent}" stroke-width="5" stroke-linejoin="round"/>
          <path d="M1011 191h169m-169 58h112" stroke="{accent}"/>
        </g>
      </g>
    """
    return svg(
        1280, height, "LoopSieve — local verification for coding workflows", body
    )


def concepts():
    return svg(
        780,
        176,
        "Three LoopSieve mark studies",
        f"""
        <rect width="780" height="176" fill="{CANVAS}"/>
        <path d="M260 24v126m260-126v126" stroke="{RULE}"/>
        <g transform="translate(82 18)">{mark()}</g>
        <g transform="translate(342 18)" fill="none" stroke-width="7" stroke-linecap="round">
          <path d="M12 26h26l32 22M12 48h58M12 70h26l32-22" stroke="{INK}"/>
          <path d="M68 48h16" stroke="{TEAL}"/>
        </g>
        <g transform="translate(602 18)" fill="none" stroke-width="7" stroke-linejoin="round">
          <path d="M20 15h52v66H20zM34 30h23m-23 14h23" stroke="{INK}"/>
          <path d="m34 60 8 7 14-15" stroke="{TEAL}"/>
        </g>
        <g font-family="Liberation Sans, Arial, sans-serif" font-size="17" text-anchor="middle" fill="{INK}">
          <text x="130" y="145">Loop and delta</text>
          <text x="390" y="145">Signal merge</text>
          <text x="650" y="145">Evidence card</text>
        </g>
        """,
    )


def export_png(source, filename, width):
    result = subprocess.run(
        ["rsvg-convert", "--width", str(width)],
        input=source.encode(),
        check=True,
        capture_output=True,
    )
    (OUT / filename).write_bytes(result.stdout)


def main():
    OUT.mkdir(exist_ok=True, parents=True)
    light = lockup(INK, TEAL, MUTED)
    dark = lockup(PAPER, MINT, FOG)
    icon = svg(96, 96, "LoopSieve icon", mark())
    for filename, source in {
        "logo.svg": light,
        "logo-light.svg": light,
        "logo-dark.svg": dark,
        "icon.svg": icon,
        "concepts.svg": concepts(),
    }.items():
        (OUT / filename).write_text(source, encoding="utf-8")
    for source, filename, width in (
        (light, "logo.png", 730),
        (icon, "icon-512.png", 512),
        (wide(False), "banner.png", 1280),
        (wide(True), "social-preview.png", 1280),
    ):
        export_png(source, filename, width)


if __name__ == "__main__":
    main()
