"""Generate the story-overlay illustrations for the email + slack demos.

Uses the Gemini Flash Image model via OpenRouter (the same `google/gemini-3.1-flash-image-preview`
the user specified). Saves PNG first, then shells out to `cwebp` for the
final WebP at quality 78 to hit the same 50-130 KB size envelope the
aperture story uses.

Run:
  OPENROUTER_API_KEY=... python3 scripts/gen_story_images.py
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
# OpenRouter sometimes routes "3.1-flash-image-preview" through to the
# closest available Google image model (2.5-flash-image-preview today,
# nano-banana yesterday). If the literal name 404s, we'll fall back.
FALLBACK_MODEL = "google/gemini-2.5-flash-image-preview"
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

STORY_DIR = Path(__file__).resolve().parent.parent / "manthan-ui" / "public" / "story"

# Universal style anchor every prompt opens with. Mirrors the Aperture
# story's editorial-painterly look: cinematic, muted, atmospheric, no
# in-frame text, 16:9 landscape, painted-feel rather than photo-real so
# it sits inside the dark UI without screaming.
STYLE = (
    "Cinematic editorial illustration in the style of a New York Times "
    "long-read header image. Painterly, slightly granular, soft brushwork. "
    "Muted palette: deep navy, warm bone, dusty terracotta, a single amber "
    "accent. 16:9 landscape, 1600x894. Dramatic light from one off-frame "
    "source. Atmospheric, not literal. No text, no logos, no UI screens, "
    "no readable typography anywhere in the frame. No watermarks. Painted "
    "rather than photo-real. Shallow depth of field on the subject. The "
    "mood is quiet weight, not panic."
)

# Per-image scene prompts. The keys map to filenames inside the story's
# subdirectory. Slide 6 in each story re-uses slide 5's image, so we
# only generate five unique images per story.
SCENES: dict[str, dict[str, str]] = {
    "maya/01-the-email-lands.webp": {
        "scene": (
            "An over-the-shoulder view of a single email envelope landing "
            "softly on a wide desk made of warm bone-colored paper. The "
            "envelope is small and tasteful with no visible text. Around "
            "it, dozens of similar envelopes lie in stacks of varying "
            "heights, suggesting an overnight inbox, but the single fresh "
            "envelope catches the only direct light from a desk lamp. The "
            "rest of the desk is in soft shadow. Early-morning light. A "
            "ceramic mug at the edge of the frame, still steaming. The "
            "single envelope is the moral center of the image."
        )
    },
    "maya/02-the-cost-of-waiting.webp": {
        "scene": (
            "A floating analog clock face hovers in soft focus, taking up "
            "the right half of the frame. Its second hand catches the "
            "light. Below and to the left, a single small coin tips on "
            "its edge, mid-fall, throwing a long shadow. The background "
            "is a textured warm bone wall with subtle painterly grain. "
            "The composition reads: time is the asset bleeding out. No "
            "numbers on the clock are legible. The mood is quiet "
            "urgency, not crisis."
        )
    },
    "maya/03-four-systems.webp": {
        "scene": (
            "Four glass panes float in space at slightly different depths "
            "and angles, suspended against a dark navy void. Each pane "
            "glows with a soft, distinct amber, terracotta, sage, or "
            "cool-blue light from within, but none of them reveal "
            "details. They are clearly separate, not connected. A single "
            "translucent thread of light passes through all four panes "
            "in sequence, joining them. No text or UI on the panes. The "
            "joining thread is the moral subject: scattered systems, one "
            "answer, only visible if you can read them all together."
        )
    },
    "maya/04-the-old-way.webp": {
        "scene": (
            "A weary support agent seen from behind, mid-thirties, "
            "shoulders softly slumped, sitting at a desk in a small "
            "pool of warm desk-lamp light. In front of them, four "
            "translucent floating panes hover at uneven angles, each "
            "glowing softly but unreadable, none of them aligned with "
            "the others. The agent reaches toward one with one hand "
            "while the others drift just out of reach. The room behind "
            "is in deep shadow. The mood is endurance, not "
            "frustration. Painterly, not photo-real. No text anywhere."
        )
    },
    "maya/05-autonomous-lane.webp": {
        "scene": (
            "A single warm amber line of light flows in a clean unbroken "
            "arc from left to right across a calm bone-and-navy "
            "background. It passes through five small floating glass "
            "shapes (each a different muted color) and emerges on the "
            "right as a single resolved point of light. The arc is "
            "decisive and elegant, suggesting one path through many "
            "systems. No characters in the frame. The mood is quiet "
            "competence, not flashy. No text, no logos, no UI."
        )
    },
    "vermillion/01-cfo-pings-slack.webp": {
        "scene": (
            "A close-cropped over-the-shoulder view of an executive (no "
            "face visible) holding a phone in one hand, the other hand "
            "resting tense on a polished walnut conference table. The "
            "phone screen is blurred warm light, no readable text. "
            "Through a wall of windows behind, a city skyline at dusk in "
            "deep blue and amber. A single accent pin of red light on "
            "the phone suggests something just landed. The atmosphere "
            "is high-stakes calm, the moment after a notification but "
            "before the response. Painterly, editorial."
        )
    },
    "vermillion/02-two-truths.webp": {
        "scene": (
            "Two pieces of vellum paper float midair against a navy "
            "void, partially overlapping. The top sheet is slightly "
            "older and bears a single faded amber wax-seal impression "
            "at its corner; the bottom sheet is fresher and bears a "
            "small clean signature mark at its corner. Neither sheet "
            "has legible writing on it. A single beam of soft light "
            "falls between them, catching the older seal first. The "
            "composition reads: two valid documents, one of them is "
            "the active one. Painterly, soft grain. No text."
        )
    },
    "vermillion/03-four-places.webp": {
        "scene": (
            "An aerial map-like flat-lay of four small glowing objects "
            "scattered across a wide dark wood table at uneven "
            "distances: a small payment card lying flat, a folded "
            "vellum letter, a tiny phone with a single chat bubble "
            "glow, and a small open ledger book. Each object glows "
            "softly in its own muted color. A faint amber line begins "
            "to trace between them in mid-air, only partially drawn. "
            "Warm overhead light, deep shadows around the table edges. "
            "No text, no logos. The objects are clearly separate but a "
            "reader can see the line forming."
        )
    },
    "vermillion/04-chase-colleagues.webp": {
        "scene": (
            "Five small silhouetted figures stand in a long thin "
            "horizontal line on a vast empty stage of warm bone paper, "
            "each holding a single small lantern that glows softly in "
            "amber. Each figure is passing their lantern to the next, "
            "but the gap between figures is uneven and the chain bends. "
            "Long soft shadows stretch behind each one. The viewer can "
            "see the lantern light is degrading by the time it reaches "
            "the end of the line. The mood is patient exhaustion. "
            "Painterly, atmospheric, no text."
        )
    },
    "vermillion/05-manthan-in-slack.webp": {
        "scene": (
            "A single small calm figure sits cross-legged at center "
            "frame, painted in soft warm light against a deep navy "
            "void. Around the figure, five soft floating glass panes "
            "orbit at different distances, each glowing in a distinct "
            "muted color. Threads of amber light connect each pane "
            "directly to the figure's hands. The figure is in repose, "
            "not strained, suggesting that the work is happening as "
            "natural conversation. No keyboard, no screen, no devices. "
            "The mood is teammate-in-the-room, not robot-at-desk. "
            "Painterly, editorial, no text."
        )
    },
}


def post_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={**headers, "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def extract_image_b64(resp: dict[str, Any]) -> str | None:
    """OpenRouter wraps Gemini image output in choices[0].message.images[]
    with each entry shaped {type: "image_url", image_url: {url: "data:..."}}.
    Pull the first PNG/JPEG data URL we can find."""
    choices = resp.get("choices") or []
    if not choices:
        return None
    msg = choices[0].get("message") or {}
    images = msg.get("images") or []
    for img in images:
        url = (img.get("image_url") or {}).get("url") or img.get("url")
        if isinstance(url, str) and url.startswith("data:image"):
            return url.split(",", 1)[1]
    # Some routes inline the data in content as an array of parts.
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
                f"  primary model {MODEL} 404'd, retrying with {FALLBACK_MODEL}\n"
            )
            body["model"] = FALLBACK_MODEL
            resp = post_json(ENDPOINT, body, {"Authorization": f"Bearer {key}"})
        else:
            raise
    b64 = extract_image_b64(resp)
    if not b64:
        sys.stderr.write(f"  no image in response: {json.dumps(resp)[:500]}\n")
        raise RuntimeError("no image returned")
    return base64.b64decode(b64)


def to_webp(png_bytes: bytes, out_path: Path, quality: int = 78) -> int:
    """Save PNG then re-encode as WebP via the system cwebp. Returns the
    final WebP byte size."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_png = out_path.with_suffix(".tmp.png")
    tmp_png.write_bytes(png_bytes)
    # cwebp -q 78 -m 6 -mt -resize 1600 0 in.png -o out.webp
    cwebp = shutil.which("cwebp") or "/opt/homebrew/bin/cwebp"
    subprocess.check_call(
        [
            cwebp,
            "-q",
            str(quality),
            "-m",
            "6",
            "-mt",
            "-resize",
            "1600",
            "0",
            str(tmp_png),
            "-o",
            str(out_path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    tmp_png.unlink(missing_ok=True)
    return out_path.stat().st_size


def main() -> int:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        sys.stderr.write("OPENROUTER_API_KEY not set\n")
        return 1
    total_bytes = 0
    for rel, spec in SCENES.items():
        out = STORY_DIR / rel
        if out.exists():
            sys.stderr.write(f"  skip {rel} (exists, {out.stat().st_size} bytes)\n")
            total_bytes += out.stat().st_size
            continue
        sys.stderr.write(f"  gen  {rel}\n")
        prompt = f"{STYLE}\n\nScene: {spec['scene']}"
        png = call_image_model(prompt, key)
        size = to_webp(png, out)
        total_bytes += size
        sys.stderr.write(f"       -> {size} bytes\n")
        time.sleep(0.3)  # gentle on the rate-limit
    sys.stderr.write(f"\nTotal: {total_bytes / 1024:.1f} KB across {len(SCENES)} files\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
