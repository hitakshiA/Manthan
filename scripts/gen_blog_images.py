"""Generate the four blog illustrations for "Tokens are the new salary."

Design discipline borrowed from the Aperture story-overlay pipeline but
tightened per the research on AI-art-direction: a locked style anchor
copy-pasted into every prompt, explicit hex palette and lighting ratio,
negative constraints, and generated in one sitting to avoid model-patch
drift between images.

Run:
  OPENROUTER_API_KEY=... python3 scripts/gen_blog_images.py
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

MODEL = "google/gemini-3.1-flash-image-preview"
FALLBACK_MODEL = "google/gemini-2.5-flash-image-preview"
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

BLOG_DIR = Path(__file__).resolve().parent.parent / "manthan-ui" / "public" / "blog"

# Locked style anchor. Pasted verbatim at the top of every prompt. Do
# NOT paraphrase, the model treats "cinematic" and "filmic" as different
# instructions. Explicit hex values, lighting ratio, negative-space
# percentages because the research is consistent: "warm editorial" is
# meaningless instruction, "color temp 4200K, fill ratio 0.6" produces
# a series.
STYLE_ANCHOR = """
VISUAL STYLE - HARD CONSTRAINT - PASTE VERBATIM

Genre: Editorial illustration. New York Times opinion-section header
aesthetic. Painterly with visible soft brush texture and light paper
grain. Not photography. Not 3D render. Not flat vector.

Color palette (hex, no substitutions):
  primary deep navy   #0F1626  (60% of frame)
  warm bone           #EFEEE6  (25% of frame)
  amber accent        #C97B2A  (10%, used only on the moral subject)
  cool teal           #4B6B6A  (5%, used only as a counterpoint)
  no pure black, no pure white, no other hues

Lighting: one off-frame warm source at 35 degrees from upper-right.
Key-to-fill ratio 4:1. Soft directional, slight falloff toward lower-
left. No top-down lighting. No flat ambient lighting.

Composition: rule of thirds. Subject occupies 35-45 percent of the
frame. Minimum 30 percent negative space, weighted toward lower-left
quadrant. Eye-level horizon when applicable. Never center-framed.

Texture: light film grain throughout. Visible painterly edges on all
subjects. No AI-smooth surfaces. No plastic-render gloss.

Mood: quiet weight, considered, slightly grave. Not panic. Not whimsy.

Hard nos: no text anywhere in the frame, no readable typography, no
logos, no brand marks, no UI screens, no charts or graphs, no people's
faces, no watermarks, no signatures, no borders.

Aspect ratio: 16:9 landscape, 1600x894 final.
"""

# Per-image scenes. Just subject + composition. Style and palette are
# in the anchor above. Slide 1 = cover, slides 2-4 = inline.
SCENES: dict[str, dict[str, str]] = {
    "01-cover-many-to-one.webp": {
        "subject": (
            "Eight translucent painterly ribbons of subtly different muted "
            "colors stream in from the left edge of the frame at uneven "
            "angles, suggesting separate sources. They converge at a "
            "single small coral-shaped translucent lens positioned on the "
            "left-third vertical line. Past the lens, a single clean amber "
            "thread continues to the right edge of the frame, smooth and "
            "unbroken. The ribbons before the lens look frayed and "
            "uncertain. The amber thread after the lens looks decisive. "
            "The lens itself is rendered as a soft painterly fan-shape "
            "with thin branching, more suggestion than detail. Heavy "
            "negative space in the lower-left quadrant."
        ),
        "composition": "wide editorial header, 16:9, subject on left third",
    },
    "02-the-bill.webp": {
        "subject": (
            "A wide bone-colored desk surface extending across the lower "
            "two-thirds of the frame, painterly wood grain visible. From "
            "the upper-right, a stack of small warm amber coin shapes "
            "spills off the visible edge of the desk, mid-fall, caught in "
            "slow descent. The coins are abstracted, not literal, no "
            "denominations visible. A single thin cool-teal thread of "
            "light arcs upward from off-frame lower-left and catches one "
            "single coin mid-fall, suspending it. The other coins continue "
            "downward into deep shadow. The mood is quiet bleed, not "
            "panic. The teal thread is the moral subject. Heavy shadow on "
            "the lower edge of the frame."
        ),
        "composition": "wide editorial header, 16:9, action on right third",
    },
    "03-substrate.webp": {
        "subject": (
            "A small abstract coral-shape structure painted at the center "
            "of the frame, rendered as a fan of thin branching lines "
            "rising from a soft base. Six muted painterly ribbons of "
            "different earth-tone colors feed into the coral structure "
            "from the left edge of the frame, each one terminating cleanly "
            "where it touches the coral. From the right side of the coral "
            "structure, a single clean amber thread of light exits and "
            "extends to the right edge of the frame. The whole composition "
            "reads: many separate sources entering, one structured "
            "answer exiting. No motion, calm, architectural feeling. "
            "Negative space in the upper-right and lower-left quadrants."
        ),
        "composition": "wide editorial header, 16:9, subject on center vertical",
    },
    "04-conviction.webp": {
        "subject": (
            "A vast bone-colored plain stretching to a low horizon two-"
            "thirds of the way up the frame. The sky above the horizon is "
            "a deep navy gradient, slightly lighter near the horizon line "
            "suggesting dusk. On the plain, a single small silhouetted "
            "figure stands on the left-third vertical line, facing toward "
            "the right side of the frame. The figure is a painterly "
            "abstraction, no facial features, just posture and the "
            "implication of forward-looking calm. Along the horizon, a "
            "row of small amber glows scattered at uneven intervals, each "
            "one suggesting a distant fire or lantern. The mood is "
            "patient and forward-looking, not lonely. The figure casts a "
            "long soft shadow toward the lower-left."
        ),
        "composition": "wide editorial header, 16:9, figure on left third",
    },
}


def post_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={**headers, "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())


def extract_image_b64(resp: dict[str, Any]) -> str | None:
    choices = resp.get("choices") or []
    if not choices:
        return None
    msg = choices[0].get("message") or {}
    images = msg.get("images") or []
    for img in images:
        url = (img.get("image_url") or {}).get("url") or img.get("url")
        if isinstance(url, str) and url.startswith("data:image"):
            return url.split(",", 1)[1]
    content = msg.get("content")
    if isinstance(content, list):
        for part in content:
            if not isinstance(part, dict):
                continue
            url = (part.get("image_url") or {}).get("url") or part.get("url")
            if isinstance(url, str) and url.startswith("data:image"):
                return url.split(",", 1)[1]
    return None


def call_image_model(prompt: str, key: str) -> bytes:
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "modalities": ["image", "text"],
    }
    try:
        resp = post_json(ENDPOINT, body, {"Authorization": f"Bearer {key}"})
    except urllib.error.HTTPError as e:
        if e.code == 404:
            sys.stderr.write(
                f"  primary {MODEL} 404'd, retrying with {FALLBACK_MODEL}\n"
            )
            body["model"] = FALLBACK_MODEL
            resp = post_json(ENDPOINT, body, {"Authorization": f"Bearer {key}"})
        else:
            raise
    b64 = extract_image_b64(resp)
    if not b64:
        sys.stderr.write(f"  no image: {json.dumps(resp)[:400]}\n")
        raise RuntimeError("no image returned")
    return base64.b64decode(b64)


def to_webp(png_bytes: bytes, out_path: Path, quality: int = 80) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_png = out_path.with_suffix(".tmp.png")
    tmp_png.write_bytes(png_bytes)
    cwebp = shutil.which("cwebp") or "/opt/homebrew/bin/cwebp"
    subprocess.check_call(
        [
            cwebp, "-q", str(quality), "-m", "6", "-mt",
            "-resize", "1600", "0",
            str(tmp_png), "-o", str(out_path),
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    tmp_png.unlink(missing_ok=True)
    return out_path.stat().st_size


def main() -> int:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        sys.stderr.write("OPENROUTER_API_KEY not set\n")
        return 1
    sys.stderr.write(
        "Generating 4 blog illustrations with locked style anchor.\n"
        "Will skip files that already exist - delete them to regen.\n\n"
    )
    total = 0
    for fname, spec in SCENES.items():
        out = BLOG_DIR / fname
        if out.exists():
            sys.stderr.write(f"  skip  {fname} ({out.stat().st_size} bytes, exists)\n")
            total += out.stat().st_size
            continue
        prompt = (
            f"{STYLE_ANCHOR.strip()}\n\n"
            f"SUBJECT FOR THIS IMAGE:\n{spec['subject'].strip()}\n\n"
            f"COMPOSITION NOTE:\n{spec['composition'].strip()}\n\n"
            "Re-read the VISUAL STYLE block above. Match every constraint. "
            "Generate one image at 1600x894."
        )
        sys.stderr.write(f"  gen   {fname}\n")
        png = call_image_model(prompt, key)
        size = to_webp(png, out)
        total += size
        sys.stderr.write(f"        -> {size} bytes\n")
        time.sleep(0.4)
    sys.stderr.write(f"\nTotal: {total / 1024:.1f} KB across {len(SCENES)} files\n")
    sys.stderr.write(f"Output: {BLOG_DIR}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
