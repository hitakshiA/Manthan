"""Brief PDF generator - render a case brief as a polished one-page PDF.

Used by the Slack bot's "asky PDF" attachment: when Manthan posts a brief
card in Slack, it also uploads a PDF brief that operators can download
and forward without losing context.

Layout (single page):
  Header: Manthan wordmark + case short_id
  Hero:   customer + amount + decision badge
  TL;DR:  2-3 sentences
  Findings table: numbered, with confidence + source citation
  Decision rationale
  Drafted actions list
  Footer: case URL + generation timestamp

reportlab gives us crisp text and good control without needing system
deps like cairo/pango.
"""

from __future__ import annotations

import io
import json
import os
from datetime import datetime
from uuid import UUID

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
)
from reportlab.lib.enums import TA_LEFT, TA_RIGHT

from manthan_api.db import get_pool


# Color palette - calibrated to match the marketing site's "Operations Memo"
# theme. Ink black, warm paper, accent blue.
INK = colors.HexColor("#1a1a1a")
INK_MUTED = colors.HexColor("#4a4a4a")
INK_GHOST = colors.HexColor("#8a8a8a")
PAPER = colors.HexColor("#FAF9F5")
ACCENT = colors.HexColor("#2563EB")
ACCENT_SOFT = colors.HexColor("#EBF1FF")
RULE = colors.HexColor("#E2DDD3")
GOOD = colors.HexColor("#0F7B3F")
BAD = colors.HexColor("#B42318")


def _styles():
    base = getSampleStyleSheet()
    return {
        "wordmark": ParagraphStyle(
            "wordmark", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=13, textColor=INK,
            spaceAfter=0,
        ),
        "eyebrow": ParagraphStyle(
            "eyebrow", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=8, textColor=INK_GHOST,
            spaceAfter=4, leading=10,
        ),
        "hero_customer": ParagraphStyle(
            "hero_customer", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=20, textColor=INK,
            spaceAfter=0, leading=24,
        ),
        "hero_amount": ParagraphStyle(
            "hero_amount", parent=base["Normal"],
            fontName="Helvetica", fontSize=11, textColor=INK_MUTED,
            spaceAfter=0, leading=14,
        ),
        "section_title": ParagraphStyle(
            "section_title", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=9, textColor=INK_GHOST,
            spaceAfter=4, leading=12,
        ),
        "tldr": ParagraphStyle(
            "tldr", parent=base["Normal"],
            fontName="Helvetica", fontSize=11, textColor=INK,
            spaceAfter=10, leading=15, alignment=TA_LEFT,
        ),
        "finding_text": ParagraphStyle(
            "finding_text", parent=base["Normal"],
            fontName="Helvetica", fontSize=9.5, textColor=INK,
            leading=12,
        ),
        "footer": ParagraphStyle(
            "footer", parent=base["Normal"],
            fontName="Helvetica", fontSize=8, textColor=INK_GHOST,
            leading=10, alignment=TA_LEFT,
        ),
    }


# ──────────────────────────────────────────────────────────────────────
# Public entry
# ──────────────────────────────────────────────────────────────────────


async def render_brief_pdf(org_id: UUID, case_id: UUID) -> bytes:
    """Pull the case + brief + findings + actions, render a one-page PDF.

    Returns the raw PDF bytes.
    """
    async with get_pool().acquire() as conn:
        case = await conn.fetchrow(
            """
            SELECT short_id, customer_ref, amount_minor, currency,
                   decision_action, decision_amount_minor, decision_confidence,
                   trigger_surface, created_at, thread_id
            FROM cases WHERE org_id=$1 AND id=$2
            """,
            org_id, case_id,
        )
        if case is None:
            raise ValueError(f"case {case_id} not found")
        thread_id = case["thread_id"]

        brief = await conn.fetchrow(
            """
            SELECT data FROM events
            WHERE org_id=$1 AND thread_id=$2 AND type='brief_drafted'
            ORDER BY seq DESC LIMIT 1
            """,
            org_id, thread_id,
        )
        findings = await conn.fetch(
            """
            SELECT seq, text, confidence, citations
            FROM findings
            WHERE org_id=$1 AND case_id=$2
            ORDER BY seq ASC
            """,
            org_id, case_id,
        )
        actions = await conn.fetch(
            """
            SELECT type, status, payload
            FROM actions
            WHERE org_id=$1 AND case_id=$2
            ORDER BY seq ASC
            """,
            org_id, case_id,
        )

    brief_data = brief["data"] if (brief and isinstance(brief["data"], dict)) else {}
    if isinstance(brief_data, str):
        brief_data = json.loads(brief_data)

    return _render_pdf_bytes(
        short_id=case["short_id"],
        customer=case["customer_ref"] or "(unknown customer)",
        amount_minor=case["amount_minor"] or 0,
        currency=(case["currency"] or "usd").upper(),
        decision_action=case["decision_action"],
        decision_amount_minor=case["decision_amount_minor"],
        decision_confidence=float(case["decision_confidence"] or 0),
        tldr=brief_data.get("tldr") or "",
        rationale=(brief_data.get("decision") or {}).get("rationale") if isinstance(brief_data.get("decision"), dict) else "",
        findings=[
            {
                "seq": f["seq"],
                "text": f["text"],
                "confidence": float(f["confidence"] or 0),
                "citations": f["citations"] or [],
            }
            for f in findings
        ],
        actions=[
            {"type": a["type"], "status": a["status"], "payload": a["payload"] or {}}
            for a in actions
        ],
    )


# ──────────────────────────────────────────────────────────────────────
# Render
# ──────────────────────────────────────────────────────────────────────


def _render_pdf_bytes(
    *,
    short_id: str,
    customer: str,
    amount_minor: int,
    currency: str,
    decision_action: str | None,
    decision_amount_minor: int | None,
    decision_confidence: float,
    tldr: str,
    rationale: str,
    findings: list[dict],
    actions: list[dict],
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        title=f"Manthan brief - {short_id}",
        author="Manthan",
    )
    styles = _styles()
    story = []

    # Header bar: wordmark + case id
    story.append(_header_row(short_id, styles))
    story.append(Spacer(1, 14))

    # Hero: customer + amount + decision badge
    story.append(_hero_row(customer, amount_minor, currency,
                            decision_action, decision_confidence, styles))
    story.append(Spacer(1, 18))

    # TL;DR
    story.append(Paragraph("TL;DR", styles["section_title"]))
    story.append(Paragraph(_escape(tldr) or "<i>-</i>", styles["tldr"]))

    # Findings
    if findings:
        story.append(Paragraph("Findings", styles["section_title"]))
        story.append(_findings_table(findings, styles))
        story.append(Spacer(1, 12))

    # Decision rationale
    if rationale:
        story.append(Paragraph("Decision rationale", styles["section_title"]))
        story.append(Paragraph(_escape(rationale), styles["tldr"]))
        story.append(Spacer(1, 8))

    # Drafted actions
    if actions:
        story.append(Paragraph("Drafted actions", styles["section_title"]))
        story.append(_actions_table(actions, styles))
        story.append(Spacer(1, 16))

    # Footer
    web_origin = os.environ.get("WEB_APP_ORIGIN", "https://demo.manthan.quest")
    footer_text = (
        f"Open in Manthan: {web_origin}/app/case/{short_id}  ·  "
        f"Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
    )
    story.append(Paragraph(footer_text, styles["footer"]))

    doc.build(story)
    return buf.getvalue()


def _header_row(short_id: str, styles) -> Table:
    return Table(
        [[
            Paragraph(
                '<font color="#1a1a1a">Manthan</font> '
                '<font color="#8a8a8a" size="9">· Operations Memo</font>',
                styles["wordmark"],
            ),
            Paragraph(
                f'<font color="#8a8a8a">Case</font> '
                f'<font color="#1a1a1a"><b>{short_id}</b></font>',
                ParagraphStyle("hdr_right", parent=styles["wordmark"],
                               alignment=TA_RIGHT, fontSize=10),
            ),
        ]],
        colWidths=[4.6 * inch, 2.6 * inch],
        style=TableStyle([
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, RULE),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]),
    )


def _hero_row(customer, amount_minor, currency,
              action, confidence, styles) -> Table:
    amount_label = f"${amount_minor / 100:,.2f} {currency}"
    badge = _decision_badge(action or "pending", confidence, styles)
    return Table(
        [[
            [
                Paragraph(_escape(customer), styles["hero_customer"]),
                Paragraph(_escape(amount_label), styles["hero_amount"]),
            ],
            badge,
        ]],
        colWidths=[4.6 * inch, 2.6 * inch],
        style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]),
    )


def _decision_badge(action: str, confidence: float, styles):
    action_label = (action or "pending").upper()
    color_map = {
        "FIGHT": BAD,
        "REFUND": ACCENT,
        "PARTIAL_CREDIT": ACCENT,
        "ACCEPT": GOOD,
        "ESCALATE": INK_MUTED,
        "PENDING": INK_GHOST,
    }
    fill = color_map.get(action_label, INK_MUTED)
    conf_pct = f"{int(confidence * 100)}%" if confidence else "-"
    badge = Table(
        [[Paragraph(
            f'<font color="white"><b>{action_label}</b></font>'
            f'<br/><font color="white" size="8">confidence {conf_pct}</font>',
            ParagraphStyle("badge", fontName="Helvetica-Bold", fontSize=10,
                           textColor=colors.white, leading=12, alignment=TA_RIGHT),
        )]],
        colWidths=[1.8 * inch],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), fill),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROUNDEDCORNERS", [6, 6, 6, 6]),
        ]),
    )
    return badge


def _findings_table(findings: list[dict], styles) -> Table:
    rows = [["#", "Finding", "Conf", "Source"]]
    for f in findings:
        cite = (f.get("citations") or [{}])[0] if f.get("citations") else {}
        src = (cite.get("source") or "-") if isinstance(cite, dict) else "-"
        rows.append([
            str(f["seq"]),
            Paragraph(_escape(f["text"]), styles["finding_text"]),
            f"{int(f['confidence'] * 100)}%" if f["confidence"] else "-",
            src,
        ])
    tbl = Table(
        rows,
        colWidths=[0.35 * inch, 4.45 * inch, 0.6 * inch, 1.0 * inch],
        repeatRows=1,
    )
    tbl.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
        ("TEXTCOLOR", (0, 0), (-1, 0), INK_GHOST),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, RULE),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, RULE),
        ("VALIGN", (0, 1), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 1), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("FONT", (0, 1), (0, -1), "Helvetica-Bold", 9),
        ("TEXTCOLOR", (0, 1), (0, -1), ACCENT),
        ("FONT", (2, 1), (2, -1), "Helvetica", 9),
        ("TEXTCOLOR", (2, 1), (2, -1), INK_MUTED),
        ("FONT", (3, 1), (3, -1), "Helvetica", 8),
        ("TEXTCOLOR", (3, 1), (3, -1), INK_MUTED),
    ]))
    return tbl


def _actions_table(actions: list[dict], styles) -> Table:
    rows = [["Type", "Status", "Detail"]]
    for a in actions[:6]:
        payload = a.get("payload") or {}
        if isinstance(payload, str):
            payload = json.loads(payload)
        detail = (
            payload.get("description")
            or payload.get("subject")
            or payload.get("text")
            or (payload.get("charge") and f"charge {payload['charge']}")
            or "-"
        )
        rows.append([
            a["type"],
            a["status"].upper(),
            Paragraph(_escape(str(detail)[:140]), styles["finding_text"]),
        ])
    tbl = Table(
        rows,
        colWidths=[1.5 * inch, 0.8 * inch, 4.1 * inch],
        repeatRows=1,
    )
    tbl.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
        ("TEXTCOLOR", (0, 0), (-1, 0), INK_GHOST),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, RULE),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, RULE),
        ("VALIGN", (0, 1), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 1), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("FONT", (0, 1), (0, -1), "Helvetica", 9),
        ("FONT", (1, 1), (1, -1), "Helvetica-Bold", 8),
        ("TEXTCOLOR", (1, 1), (1, -1), ACCENT),
    ]))
    return tbl


def _escape(s: str) -> str:
    """Escape minimal HTML for reportlab's mini-HTML parser."""
    if s is None:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
