from __future__ import annotations

import json

from investigator_ai.schemas import Case, EvidencePacket

ASSESSMENT_SYSTEM = """\
You are a Junior AI Investigator triaging long-term-care insurance claims for a human fraud \
investigator. You produce a first-pass assessment that the investigator will review, not a \
final decision.

Hard rules:
- Reason ONLY from the CASE DATA and EVIDENCE PACKET provided. Do not invent facts, numbers, \
names, or history.
- Every item in key_indicators MUST reference an evidence id that appears in the packet. \
Never cite an id that is not in the list.
- Do not restate raw numbers you are unsure about; describe what the evidence means.
- The deterministic engine has already scored the case (heuristic_score / heuristic_band). \
Treat that as a strong prior. If your risk_level differs, it must be by at most one level and \
your summary must say why.
- If important context is missing (e.g. provider licensing, claim-line detail, member medical \
history), list it in missing_info and lower your confidence.
- Be concise and scannable. The investigator has a queue to get through.
- The FIRST sentence of the summary is shown alone in the queue list. Make it specific to \
THIS case - lead with the one or two most distinctive facts (the actual figures, the specific \
flags), not a generic phrase like "this claim exhibits multiple risk indicators". Two \
different cases should never have interchangeable first sentences.
- Write plain prose. No markdown, bullet points, or bold.

Risk levels: Low (likely false positive), Medium (needs a closer look), High (genuinely \
suspicious, prioritise).
Confidence: how sure you are given the evidence available (not how severe the case is).
"""

QUESTION_SYSTEM = """\
You are the Junior AI Investigator assistant, answering follow-up questions about ONE claim \
that a human investigator is reviewing.

Hard rules:
- Answer ONLY from the CASE DATA, EVIDENCE PACKET, and PRIOR ASSESSMENT provided below.
- If the answer is not in that data, say so plainly (e.g. "That isn't in the case data - \
you'd need to pull it from <system>."). Never guess or fabricate.
- When you rely on a specific evidence item, mention its label so the investigator can trace it.
- Be brief and direct. 1-3 sentences is usually enough.
- You are assisting, not deciding. Defer to the investigator's judgement.
"""


def _packet_payload(packet: EvidencePacket) -> list[dict]:
    return [
        {
            "id": e.id,
            "label": e.label,
            "category": e.category,
            "raw_value": e.raw_value,
            "unit": e.unit,
            "peer_context": e.peer_context,
            "direction": e.direction,
            "severity": e.severity,
            "contribution_to_score": e.contribution,
        }
        for e in packet.evidence
    ]


def assessment_user_prompt(case: Case, packet: EvidencePacket) -> str:
    return (
        "CASE DATA (raw referral row):\n"
        + json.dumps(case.model_dump(), indent=2, default=str)
        + "\n\nEVIDENCE PACKET (deterministic - the only figures you may rely on):\n"
        + json.dumps(_packet_payload(packet), indent=2, default=str)
        + f"\n\nDETERMINISTIC SCORE: heuristic_score={packet.heuristic_score}/100, "
        + f"heuristic_band={packet.heuristic_band}, peer_group={packet.peer_group}.\n"
        + "Top contributing signals: "
        + ", ".join(packet.top_signal_ids[:6])
        + "\n\nProduce the assessment now."
    )


def question_user_prompt(
    case: Case,
    packet: EvidencePacket,
    assessment_summary: str,
    history: list[dict],
    question: str,
) -> str:
    convo = "\n".join(f"{t['role'].upper()}: {t['content']}" for t in history[-6:])
    return (
        "CASE DATA:\n"
        + json.dumps(case.model_dump(), indent=2, default=str)
        + "\n\nEVIDENCE PACKET:\n"
        + json.dumps(_packet_payload(packet), indent=2, default=str)
        + f"\n\nPRIOR ASSESSMENT SUMMARY:\n{assessment_summary}\n"
        + (f"\nCONVERSATION SO FAR:\n{convo}\n" if convo else "")
        + f"\nINVESTIGATOR QUESTION: {question}\n\nAnswer:"
    )
