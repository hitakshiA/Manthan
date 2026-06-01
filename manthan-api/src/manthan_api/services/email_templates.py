"""Manthan-branded HTML email templates.

Three templates share one editorial direction (warm-dark hero band with
Manthan wordmark, Spectral display fallback, accent stripe, hairline
footer - same tokens the webui uses):

  • render_ack_email()         - "Got your message, investigating"
                                  sent immediately on case_opened from email
  • render_resolution_email()  - "Here's what we did" - sent after the
                                  operator approves the agent's actions
  • render_action_email()      - generic mid-case agent-drafted message
                                  (e.g. "Can you confirm the date you
                                  saw the duplicate charge?")

Design discipline:
  - Inline CSS only (no <style> blocks) - most clients strip them.
  - System font stack; Spectral as the editorial accent where supported.
  - Single accent color (#3a8a55 - accent token equivalent in OKLCH).
  - Max-width 560px so it reads well on phones AND in a wide preview.
  - All copy goes through `_escape()` to prevent XSS via Stripe dispute
    IDs / customer names containing accidental HTML.
  - No internal-policy strings, no agent-only fields. The caller decides
    what to include - these helpers JUST style.
"""

from __future__ import annotations

import html
import re
from datetime import datetime
from typing import Sequence


# ──────────────────────────────────────────────────────────────────────
# Editorial tokens - kept in sync with manthan-ui globals.css
# ──────────────────────────────────────────────────────────────────────


PALETTE = {
    "bg_paper":     "#f7f4ef",   # warm cream
    "bg_hero":      "#1a1a1e",   # warm near-black
    "ink_strong":   "#22222a",
    "ink_muted":    "#5a5a64",
    "ink_faint":    "#8b8b95",
    "rule":         "#e2dcd1",
    "accent":       "#3a8a55",
    "accent_ink":   "#ffffff",
    "amber":        "#c08a3a",
    "danger":       "#b34a4a",
}

FONT_BODY = (
    '-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, '
    "sans-serif"
)
FONT_DISPLAY = (
    'Spectral, "Iowan Old Style", "Charter", Georgia, '
    '"Times New Roman", serif'
)

MANTHAN_BRAND_LINE = "Manthan · billing ops, on autopilot."


# ──────────────────────────────────────────────────────────────────────
# Public renderers
# ──────────────────────────────────────────────────────────────────────


def render_ack_email(
    *,
    customer_name: str | None,
    customer_email: str,
    subject_received: str,
    case_short_id: str,
    stripe_dispute_id: str | None = None,
    estimated_minutes: int = 30,
) -> tuple[str, str]:
    """Auto-ack sent right after we receive a customer's email.

    Sketch: "I am investigating and will reply soon", plus the Stripe
    dispute ID where applicable so the customer has a paper trail.

    Returns (subject, html_body).
    """
    name = (customer_name or "").strip() or _name_from_email(customer_email)
    intro = (
        f"Thanks for writing in. I'm <strong>Manthan</strong>, the AI working "
        "alongside the billing team here - I've taken your message into our "
        f"system as case <strong>{_e(case_short_id)}</strong> and started "
        "looking into it."
    )
    detail_rows: list[tuple[str, str]] = [
        ("Subject", _e(subject_received) or "(none)"),
        ("Case", _e(case_short_id)),
    ]
    if stripe_dispute_id:
        detail_rows.append(("Stripe dispute", _e(stripe_dispute_id)))

    eta = (
        f"You should hear back from us within <strong>~{estimated_minutes} "
        "minutes</strong>"
        if estimated_minutes < 60
        else "You should hear back from us shortly"
    )

    body_blocks = [
        _paragraph(f"Hi {_e(name)},"),
        _paragraph(intro),
        _detail_table(detail_rows),
        _paragraph(
            f"{eta}. If you have anything else to add to the case - receipts, "
            "screenshots, anything - just reply to this email and it'll attach "
            "to the same case automatically."
        ),
        _signoff("- Manthan"),
    ]

    html_body = _shell(
        preheader=f"Got your message - investigating · {case_short_id}",
        hero_eyebrow="Case opened",
        hero_title=f"We're on it.",
        content_html="".join(body_blocks),
    )

    subj = f"Re: {subject_received} · we're on it [{case_short_id}]"
    return subj, html_body


def render_resolution_email(
    *,
    customer_name: str | None,
    customer_email: str,
    headline: str,
    body_paragraphs: Sequence[str],
    case_short_id: str,
    stripe_dispute_url: str | None = None,
    signed_by: str | None = None,
    subject_override: str | None = None,
) -> tuple[str, str]:
    """Outbound resolution email - the "here's what we did" message.

    `headline` should be ONE plain-English sentence the customer reads
    first ("We've refunded the duplicate $89 charge."). `body_paragraphs`
    is a short list of 1-3 paragraphs giving context. Never include
    internal policy IDs, agent-only fields, or run metadata - those are
    filtered out at the agent prompt layer, but defend in depth: callers
    must hand us copy that's customer-safe.

    Returns (subject, html_body).
    """
    name = (customer_name or "").strip() or _name_from_email(customer_email)

    body_html: list[str] = [
        _paragraph(f"Hi {_e(name)},"),
        _paragraph(_e(headline), font_size=16, weight=500),
    ]
    for p in body_paragraphs:
        body_html.append(_paragraph(_e(p)))

    if stripe_dispute_url:
        body_html.append(
            _button(
                href=stripe_dispute_url,
                label="View the Stripe record",
            )
        )

    body_html.append(
        _paragraph(
            "If anything's off - or if there's something else we should "
            "have caught - just reply to this email and it'll route back "
            "to the same case.",
            color=PALETTE["ink_muted"],
            font_size=13,
        )
    )

    signer = signed_by or "Manthan, on behalf of the billing team"
    body_html.append(_signoff(f"- {_e(signer)}"))

    html_body = _shell(
        preheader=_preheader_from(headline),
        hero_eyebrow="Case resolved",
        hero_title="Here's what we did.",
        content_html="".join(body_html),
        footer_extra=f"Case reference: <strong>{_e(case_short_id)}</strong>",
    )

    subj = subject_override or f"Update on your case · {case_short_id}"
    return subj, html_body


def render_action_email(
    *,
    customer_name: str | None,
    customer_email: str,
    purpose: str,
    headline: str,
    body_paragraphs: Sequence[str],
    case_short_id: str,
    call_to_action: dict[str, str] | None = None,
    stripe_dispute_url: str | None = None,
    signed_by: str | None = None,
    subject_override: str | None = None,
) -> tuple[str, str]:
    """Generic mid-investigation email - when the agent decides it needs
    something from the customer (e.g. "could you confirm the date of the
    duplicate charge?").

    `purpose` is the eyebrow label ("Quick question", "Update", etc.).
    `call_to_action` is `{label, href}` rendered as the button.

    Returns (subject, html_body).
    """
    name = (customer_name or "").strip() or _name_from_email(customer_email)

    body_html: list[str] = [
        _paragraph(f"Hi {_e(name)},"),
        _paragraph(_e(headline), font_size=16, weight=500),
    ]
    for p in body_paragraphs:
        body_html.append(_paragraph(_e(p)))

    if call_to_action and call_to_action.get("href"):
        body_html.append(
            _button(
                href=call_to_action["href"],
                label=call_to_action.get("label", "Open"),
            )
        )
    if stripe_dispute_url:
        body_html.append(
            _paragraph(
                f'For context: '
                f'<a href="{_e(stripe_dispute_url)}" '
                f'style="color:{PALETTE["accent"]};text-decoration:underline">'
                "view the Stripe record</a>.",
                color=PALETTE["ink_muted"],
                font_size=13,
            )
        )

    body_html.append(
        _paragraph(
            "Replying to this email lands directly back on the case.",
            color=PALETTE["ink_faint"],
            font_size=12,
        )
    )

    signer = signed_by or "Manthan"
    body_html.append(_signoff(f"- {_e(signer)}"))

    html_body = _shell(
        preheader=_preheader_from(headline),
        hero_eyebrow=purpose,
        hero_title="A quick note.",
        content_html="".join(body_html),
        footer_extra=f"Case reference: <strong>{_e(case_short_id)}</strong>",
    )

    subj = subject_override or f"{purpose} · {case_short_id}"
    return subj, html_body


# ──────────────────────────────────────────────────────────────────────
# Shell + primitives
# ──────────────────────────────────────────────────────────────────────


def _shell(
    *,
    preheader: str,
    hero_eyebrow: str,
    hero_title: str,
    content_html: str,
    footer_extra: str | None = None,
) -> str:
    """The single outer HTML used by every template. Hairlines, warm
    cream paper, single accent stripe."""
    year = datetime.utcnow().year
    return f"""\
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Manthan</title>
</head>
<body style="margin:0;padding:0;background:{PALETTE['bg_paper']};font-family:{FONT_BODY};color:{PALETTE['ink_strong']};-webkit-font-smoothing:antialiased;">
  <!-- preheader (hidden from view but shown in inbox preview) -->
  <div style="display:none;font-size:1px;line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;mso-hide:all;visibility:hidden;color:transparent;">{_e(preheader)}</div>

  <table role="presentation" width="100%" border="0" cellpadding="0" cellspacing="0" style="background:{PALETTE['bg_paper']};">
    <tr>
      <td align="center" style="padding:40px 16px 24px 16px;">
        <table role="presentation" width="560" border="0" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#ffffff;border:1px solid {PALETTE['rule']};border-radius:6px;overflow:hidden;">
          <!-- Hero band -->
          <tr>
            <td style="background:{PALETTE['bg_hero']};padding:24px 28px;color:#efece4;">
              <div style="font-family:{FONT_BODY};font-size:11px;letter-spacing:0.14em;text-transform:uppercase;opacity:0.65;">{_e(hero_eyebrow)}</div>
              <div style="font-family:{FONT_DISPLAY};font-size:26px;line-height:1.15;letter-spacing:-0.01em;margin-top:8px;">
                {_e(hero_title)}
              </div>
            </td>
          </tr>
          <!-- Accent stripe -->
          <tr>
            <td style="height:3px;background:{PALETTE['accent']};line-height:3px;font-size:0;">&nbsp;</td>
          </tr>
          <!-- Body content -->
          <tr>
            <td style="padding:28px 28px 8px 28px;font-size:14.5px;line-height:1.62;color:{PALETTE['ink_strong']};">
              {content_html}
            </td>
          </tr>
          <!-- Hairline footer -->
          <tr>
            <td style="border-top:1px solid {PALETTE['rule']};padding:18px 28px 22px 28px;font-size:11.5px;color:{PALETTE['ink_faint']};">
              <div style="font-family:{FONT_DISPLAY};font-style:italic;font-size:13px;color:{PALETTE['ink_muted']};margin-bottom:4px;">
                {MANTHAN_BRAND_LINE}
              </div>
              {f'<div style="margin-top:6px;">{footer_extra}</div>' if footer_extra else ''}
              <div style="margin-top:6px;">
                © {year} Manthan · automated assistance, reviewed by humans before action fires.
              </div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


def _paragraph(html_body: str, *, color: str | None = None, font_size: int = 14, weight: int = 400) -> str:
    color = color or PALETTE["ink_strong"]
    return (
        f'<p style="margin:0 0 14px 0;font-size:{font_size}px;'
        f"line-height:1.6;color:{color};font-weight:{weight};\">"
        f"{html_body}</p>"
    )


def _detail_table(rows: Sequence[tuple[str, str]]) -> str:
    cells = []
    for label, value in rows:
        cells.append(
            f"""\
<tr>
  <td style="padding:8px 14px 8px 0;font-size:11px;text-transform:uppercase;letter-spacing:0.1em;color:{PALETTE['ink_faint']};white-space:nowrap;vertical-align:top;border-bottom:1px solid {PALETTE['rule']};">{_e(label)}</td>
  <td style="padding:8px 0;font-size:13.5px;color:{PALETTE['ink_strong']};font-family:Menlo,Consolas,'SF Mono',monospace;border-bottom:1px solid {PALETTE['rule']};">{value}</td>
</tr>"""
        )
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="margin:8px 0 18px 0;border-top:1px solid {PALETTE["rule"]};">'
        f"{''.join(cells)}</table>"
    )


def _button(*, href: str, label: str) -> str:
    return f"""\
<div style="margin:18px 0 22px 0;">
  <a href="{_e(href)}" target="_blank" style="display:inline-block;padding:10px 18px;background:{PALETTE['accent']};color:{PALETTE['accent_ink']};font-size:13px;font-weight:500;letter-spacing:0.02em;text-decoration:none;border-radius:4px;">
    {_e(label)} ↗
  </a>
</div>
"""


def _signoff(text: str) -> str:
    return (
        f'<p style="margin:24px 0 6px 0;font-family:{FONT_DISPLAY};'
        f'font-style:italic;font-size:14px;color:{PALETTE["ink_muted"]};">'
        f"{_e(text)}</p>"
    )


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _e(s: str | None) -> str:
    """HTML-escape user-supplied content."""
    if s is None:
        return ""
    return html.escape(str(s), quote=True)


def _name_from_email(email: str) -> str:
    """Derive a fallback display name from an email address.
       'jane.doe@example.com' → 'Jane'.  Returns 'there' if we can't get
       anything useful."""
    if not email or "@" not in email:
        return "there"
    local = email.split("@", 1)[0]
    # take the first chunk before . _ + - and Title-case it
    first = re.split(r"[._+\-]", local)[0]
    return first.title() if first else "there"


def _preheader_from(text: str) -> str:
    """Trim a sentence into a ~110-char preheader."""
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= 110:
        return text
    return text[:107].rstrip() + "…"


def render_welcome_email(
    *,
    first_name: str | None,
    email: str,
    demo_url: str,
    founder_email: str = "akash@miny-labs.com",
) -> tuple[str, str]:
    """The MVP welcome email - fired on `user.created` from Clerk.

    Direction: borrow the *landing-page hero* feel - warm-near-black
    expanse, the concentric-arcs Manthan glyph at hero size, the
    "Beta · Manthan v1 …" pill, BIG Spectral italic display headline
    with generous silence, iridescent CTA, editorial italic voice. Then
    a paper-cream body with hairline section dividers (not bullet lists)
    and a personal note that reads like one person wrote it.

    Returns (subject, html_body).
    """
    name = (first_name or "").strip() or _name_from_email(email)

    # ── Body, written as connected editorial beats, not a bulleted SaaS
    #    welcome. The lead is in display italic; the rest sets the tone
    #    one paragraph at a time. ──

    content = "".join([
        # Personal greeting - quiet, no eyebrow.
        _paragraph(
            f"Hi {_e(name)},",
            font_size=14,
            color=PALETTE["ink_muted"],
        ),
        # Lead - italic display, a memo lede.
        f'<p style="margin:6px 0 22px 0;font-family:{FONT_DISPLAY};font-style:italic;'
        f'font-size:19px;line-height:1.45;color:{PALETTE["ink_strong"]};'
        f'letter-spacing:-0.005em;">'
        "Thanks for trying Manthan while it&rsquo;s still raw."
        "</p>",
        _paragraph(
            "We&rsquo;re in <strong>MVP phase</strong> - a few things are "
            "intentional, and a few will get sharper over the coming weeks. "
            "What&rsquo;s already there is a real agent, joining real billing "
            "data across eleven connected sources, drafting actions you can "
            "approve, deny, or argue with."
        ),

        # Hairline + editorial section eyebrow
        _hairline(),
        _editorial_eyebrow("What's already in the demo"),

        # Three beats, but rendered as connected paragraphs with thin
        # accent rules - less bullet-list, more memo.
        _editorial_beats([
            (
                "01",
                "A live inbox",
                "with cases waiting on a nod. Click any card to watch "
                "the agent stitch together evidence across Stripe, "
                "Salesforce, HubSpot, Intercom, and the rest.",
            ),
            (
                "02",
                "Three pre-baked scenarios",
                "to fire from the top right - Quill Logistics chargeback, "
                "Vermillion seat dispute, Maya autonomous duplicate. Each "
                "one is a real case the agent investigates from scratch.",
            ),
            (
                "03",
                "Every claim is citable",
                "every action is reversible, every reply is in your "
                "voice - never policy-leaky, never agent jargon.",
            ),
        ]),

        _hairline(),

        # The ask - quiet but unambiguous. Note: this mailbox doesn't
        # accept inbound; route them to the founder directly.
        _editorial_eyebrow("If you want priority access"),
        _paragraph(
            "When we ship v1 you&rsquo;ll get first pick - but I&rsquo;d "
            "love to talk before then. Write me directly at "
            f'<a href="mailto:{_e(founder_email)}" '
            f'style="color:{PALETTE["accent"]};text-decoration:underline;font-weight:500;">'
            f"{_e(founder_email)}</a>. "
            "I read every one.",
            font_size=14.5,
        ),

        # Iridescent CTA - the landing-page pill, ported to email.
        _iridescent_button(href=demo_url, label="Open the demo"),

        # Closer
        _paragraph(
            "Thanks for the trust. There&rsquo;s a lot to do, and you "
            "saying yes early matters more than you probably realise.",
            color=PALETTE["ink_muted"],
            font_size=13.5,
        ),

        _founder_signoff(
            name="Akash",
            role="Founder, Manthan",
            email=founder_email,
        ),
    ])

    html_body = _welcome_shell(
        preheader=(
            "You're in early. Manthan is in MVP - here's what's in the "
            "demo and how to lock in priority access."
        ),
        content_html=content,
    )
    subj = "You're in early - welcome to Manthan"
    return subj, html_body


def _welcome_shell(*, preheader: str, content_html: str) -> str:
    """Cinematic shell adopting landing-page treatments: warm-near-black
    hero with the concentric-arcs glyph sitting in generous silence,
    a 'Beta · Manthan v1 · early access' liquid-glass pill, BIG
    Spectral italic display headline, accent emerald stripe, then a
    paper-cream body with hairline dividers."""
    year = datetime.utcnow().year

    # PNG glyph hosted on the frontend's CDN. Gmail and most email
    # clients block inline <svg> entirely (security policy strips the
    # element), so we serve a pre-rendered PNG of the same three-arc
    # logo and reference it via <img>. The asset is a 240px retina
    # render displayed at 60px - generated by a Pillow script and
    # committed at manthan-ui/public/logo.png so it survives rebuilds.
    glyph = (
        '<img src="https://manthan.quest/logo.png" '
        'width="60" height="60" alt="Manthan" '
        'style="display:block;width:60px;height:60px;border:0;outline:none;'
        'text-decoration:none;" />'
    )

    # The "Beta · Manthan v1 · now accepting design partners" pill from
    # the landing hero, translated to email-safe inline HTML. No
    # backdrop-filter (not supported in mail) - just a subtle ink-on-ink
    # surface with a 1px hairline.
    beta_pill = (
        '<table role="presentation" cellpadding="0" cellspacing="0" '
        'style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.10);'
        'border-radius:8px;margin:0 auto;">'
        "<tr>"
        '<td style="padding:6px 8px 6px 8px;">'
        '<span style="display:inline-block;background:#ffffff;color:#000000;'
        'padding:3px 8px 4px 8px;border-radius:5px;font-size:11px;font-weight:600;'
        'letter-spacing:0.02em;">MVP</span>'
        "</td>"
        '<td style="padding:6px 12px 6px 4px;">'
        f'<span style="font-family:{FONT_BODY};font-size:12.5px;font-weight:500;'
        'color:rgba(255,255,255,0.62);white-space:nowrap;">'
        "Manthan v1 · now accepting design partners"
        "</span>"
        "</td>"
        "</tr>"
        "</table>"
    )

    return f"""\
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Welcome to Manthan</title>
</head>
<body style="margin:0;padding:0;background:{PALETTE['bg_paper']};font-family:{FONT_BODY};color:{PALETTE['ink_strong']};-webkit-font-smoothing:antialiased;">
  <!-- preheader (hidden, shown in inbox preview) -->
  <div style="display:none;font-size:1px;line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;mso-hide:all;visibility:hidden;color:transparent;">{_e(preheader)}</div>

  <table role="presentation" width="100%" border="0" cellpadding="0" cellspacing="0" style="background:{PALETTE['bg_paper']};">
    <tr>
      <td align="center" style="padding:44px 16px 28px 16px;">
        <table role="presentation" width="620" border="0" cellpadding="0" cellspacing="0" style="max-width:620px;width:100%;background:#ffffff;border:1px solid {PALETTE['rule']};border-radius:10px;overflow:hidden;">

          <!-- ── Hero band - landing-feel: warm near-black, generous silence, big glyph, Spectral italic ── -->
          <tr>
            <td align="center" style="background:{PALETTE['bg_hero']};padding:56px 32px 60px 32px;color:#efece4;">
              <!-- Glyph -->
              <div style="display:inline-block;margin-bottom:22px;">{glyph}</div>
              <!-- Beta pill -->
              <div style="margin-bottom:28px;">
                {beta_pill}
              </div>
              <!-- Big display headline - Spectral italic, dramatic -->
              <div style="font-family:{FONT_DISPLAY};font-style:italic;font-size:38px;line-height:1.04;letter-spacing:-0.014em;color:#efece4;">
                You&rsquo;re in early.
              </div>
              <!-- Subtitle - quieter italic Spectral, breathing room -->
              <div style="font-family:{FONT_DISPLAY};font-style:italic;font-size:15px;line-height:1.52;color:#a8a294;margin-top:14px;max-width:420px;margin-left:auto;margin-right:auto;">
                The operations layer for revenue disputes.<br/>
                With a human in the loop.
              </div>
            </td>
          </tr>

          <!-- Accent stripe - landing's emerald hairline beneath the hero -->
          <tr>
            <td style="height:3px;background:{PALETTE['accent']};line-height:3px;font-size:0;">&nbsp;</td>
          </tr>

          <!-- ── Body - paper cream, generous padding, editorial rhythm ── -->
          <tr>
            <td style="padding:38px 40px 16px 40px;font-size:14.5px;line-height:1.62;color:{PALETTE['ink_strong']};">
              {content_html}
            </td>
          </tr>

          <!-- ── Footer - italic Spectral brand line, year, small print ── -->
          <tr>
            <td style="border-top:1px solid {PALETTE['rule']};padding:22px 40px 26px 40px;font-size:11.5px;color:{PALETTE['ink_faint']};">
              <div style="font-family:{FONT_DISPLAY};font-style:italic;font-size:14px;color:{PALETTE['ink_muted']};margin-bottom:6px;">
                {MANTHAN_BRAND_LINE}
              </div>
              <div style="margin-top:6px;">
                © {year} Manthan · You&rsquo;re receiving this because you signed up at
                <a href="https://demo.manthan.quest" style="color:{PALETTE['ink_muted']};text-decoration:underline;">demo.manthan.quest</a>.
              </div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


def _editorial_beats(beats: list[tuple[str, str, str]]) -> str:
    """Numbered editorial beats - `(numeral, headline, body)` - separated
    by silence, not bullets. Each row has a mono numeral on the left,
    italic Spectral headline next to it, then a flowing body underneath.

    Reads like a brief, not a feature list."""
    rows = []
    for numeral, headline, body in beats:
        rows.append(
            f"""\
<tr>
  <td style="padding:14px 0 18px 0;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td style="width:36px;vertical-align:top;padding-top:4px;">
          <span style="font-family:Menlo,Consolas,'SF Mono',monospace;font-size:11px;color:{PALETTE['ink_faint']};letter-spacing:0.04em;">
            {_e(numeral)}
          </span>
        </td>
        <td>
          <div style="font-family:{FONT_DISPLAY};font-style:italic;font-size:18px;line-height:1.3;color:{PALETTE['ink_strong']};letter-spacing:-0.004em;">
            {_e(headline)}
          </div>
          <div style="font-size:13.5px;color:{PALETTE['ink_muted']};line-height:1.6;margin-top:6px;">
            {_e(body)}
          </div>
        </td>
      </tr>
    </table>
  </td>
</tr>"""
        )
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="margin:6px 0 6px 0;">'
        f"{''.join(rows)}</table>"
    )


def _editorial_eyebrow(text: str) -> str:
    """Small uppercase section label - same eyebrow treatment the webui
    uses across the workspace."""
    return (
        '<div style="font-size:11px;font-weight:500;letter-spacing:0.14em;'
        f"text-transform:uppercase;color:{PALETTE['ink_faint']};margin:8px 0 6px 0;\">"
        f"{_e(text)}</div>"
    )


def _hairline() -> str:
    """Editorial section divider - full-width 1px rule, generous margin
    on both sides. Replaces the bullet/spacer patterns of generic emails."""
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="margin:28px 0 28px 0;"><tr><td style="height:1px;background:{PALETTE["rule"]};line-height:1px;font-size:0;">&nbsp;</td></tr></table>'
    )


def _iridescent_button(*, href: str, label: str) -> str:
    """The landing-page CTA pill, ported to email.

    Same pink → lavender → ice-blue → mint gradient and inner-glow shadow.
    Most modern clients (Apple Mail, Gmail web/iOS/Android, Outlook 2019+)
    honour linear-gradient on `background` and box-shadow on inline links.
    Outlook 2007/2013 fall back to a flat-cream button - still legible.
    """
    iridescent = (
        "linear-gradient(95deg, #f5c0d5 0%, #d8c0e8 30%, "
        "#b8d8ee 65%, #c8e8d5 100%)"
    )
    fallback_bg = "#e8dcec"  # average of the four stops, for non-gradient clients
    return f"""\
<table role="presentation" cellpadding="0" cellspacing="0" style="margin:24px 0 22px 0;">
  <tr>
    <td>
      <!--[if mso]>
      <a href="{_e(href)}" style="display:inline-block;background:{fallback_bg};color:#000;padding:14px 26px;border-radius:999px;text-decoration:none;font-weight:500;">{_e(label)} →</a>
      <![endif]-->
      <!--[if !mso]><!-- -->
      <a href="{_e(href)}" target="_blank" style="display:inline-block;padding:13px 28px;background:{fallback_bg};background:{iridescent};color:#000000;font-size:15px;font-weight:500;letter-spacing:-0.002em;text-decoration:none;border-radius:999px;box-shadow:inset 0 1px 0 rgba(255,255,255,0.5), 0 8px 24px rgba(200,180,255,0.18);">
        {_e(label)} <span style="display:inline-block;margin-left:4px;">&rarr;</span>
      </a>
      <!--<![endif]-->
    </td>
  </tr>
</table>
"""


def _founder_signoff(*, name: str, role: str, email: str) -> str:
    """Personal sign-off - name in big Spectral italic, role and email
    below in muted body type, with the accent emerald core glyph to the
    left mimicking the Manthan mark."""
    return f"""\
<table role="presentation" cellpadding="0" cellspacing="0" style="margin:24px 0 4px 0;">
  <tr>
    <td style="vertical-align:middle;padding-right:12px;">
      <span style="display:inline-block;width:12px;height:12px;background:{PALETTE['accent']};border-radius:3px;"></span>
    </td>
    <td style="vertical-align:middle;">
      <div style="font-family:{FONT_DISPLAY};font-style:italic;font-size:17px;color:{PALETTE['ink_strong']};letter-spacing:-0.004em;">
        - {_e(name)}
      </div>
      <div style="font-size:12px;color:{PALETTE['ink_faint']};margin-top:3px;">
        {_e(role)} ·
        <a href="mailto:{_e(email)}" style="color:{PALETTE['ink_muted']};text-decoration:underline;">
          {_e(email)}
        </a>
      </div>
    </td>
  </tr>
</table>
"""


def render_plain_text_fallback(html_body: str) -> str:
    """Very crude HTML→text - Resend takes the html field and most clients
    show that; we still provide a text fallback for accessibility and
    spam-filter friendliness. Strips tags, collapses whitespace."""
    text = re.sub(r"<style[^>]*>.*?</style>", "", html_body, flags=re.S | re.I)
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p\s*>", "\n\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    # collapse runs of blanks
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
