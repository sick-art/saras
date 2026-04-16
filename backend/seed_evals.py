#!/usr/bin/env python3
"""Seed script — sample evals dataset with multi-turn agentic conversations.

Creates:
  • 1 Dataset  "Customer Support Golden Set" (3 items)
  • 1 EvalSuite "Customer Support Quality" (5 metrics)
  • 1 completed EvalRun with full per-turn + whole-conversation scores

Conversations use the Aria e-commerce support agent persona.

Usage (from backend/):
    uv run python seed_evals.py
    # or
    python seed_evals.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Add backend to path so saras package resolves
sys.path.insert(0, str(Path(__file__).parent))

from ulid import new as ulid_new

from saras.db.models import (
    Agent,
    Dataset,
    DatasetItem,
    EvalResult,
    EvalRun,
    EvalSuite,
    Project,
)
from saras.db.postgres import AsyncSessionLocal


# ── Helpers ────────────────────────────────────────────────────────────────────

def uid() -> str:
    return str(ulid_new())


def now() -> datetime:
    return datetime.now(timezone.utc)


# ── Metric set YAML ────────────────────────────────────────────────────────────

METRIC_SET_YAML = """\
metrics:
  - preset: goal_completion
  - preset: hallucination_detection
  - preset: tool_call_accuracy
  - preset: slot_fill_efficiency
  - preset: tone_consistency
"""

# ── Aria agent YAML (abbreviated for seed purposes) ───────────────────────────

AGENT_YAML = """\
name: Aria — ShopFlow Support
description: E-commerce customer support agent for ShopFlow
persona:
  name: Aria
  role: Customer Support Specialist
  tone: Warm, professional, solution-focused
model:
  primary: claude-sonnet-4-6
  router: claude-haiku-4-5
tools:
  - name: Order Lookup
    description: Retrieve order details by order ID
    inputs:
      - name: order_id
        type: string
        required: true
  - name: Return Request
    description: Submit a return request for an order
    inputs:
      - name: order_id
        type: string
        required: true
      - name: reason
        type: string
        required: true
  - name: Refund Status Check
    description: Check the current status of a submitted refund
    inputs:
      - name: order_id
        type: string
        required: true
"""


# ── Conversation data ──────────────────────────────────────────────────────────

def _conv_item1(item_id: str) -> dict[str, Any]:
    """Happy-path: order tracking in 4 turns. All tools called correctly."""
    turns = [
        {
            "turn_index": 0,
            "user_message": "Hi, I need help tracking my order ORD-78234",
            "agent_content": (
                "Hi there! I'm Aria, your ShopFlow support specialist. I'd be happy to help "
                "you track your order — let me pull that up right away!\n\n"
                "I found your order **ORD-78234**. It's currently **In Transit** with FedEx "
                "(tracking: 794644792798). Your package is moving on schedule and is expected "
                "to arrive by **Wednesday, April 15th** between 9 AM – 8 PM."
            ),
            "turn_type": "response",
            "tool_calls_made": [
                {
                    "id": "call_abc001",
                    "type": "function",
                    "function": {
                        "name": "Order Lookup",
                        "arguments": json.dumps({"order_id": "ORD-78234"}),
                    },
                }
            ],
            "router_decision": {
                "condition": "order_tracking",
                "extracted_slot_values": {"order_id": "ORD-78234"},
                "unfilled_slots": [],
            },
            "input_tokens": 312,
            "output_tokens": 105,
            "cost_usd": 0.0028,
        },
        {
            "turn_index": 1,
            "user_message": "The website just shows 'In Transit'. When exactly will it arrive?",
            "agent_content": (
                "Based on the latest tracking update, your package is currently at the "
                "**Austin, TX** distribution center and was scanned this morning. Delivery is "
                "confirmed for **Wednesday, April 15th**, typically between 9 AM – 8 PM local "
                "time. FedEx will send a 30-minute heads-up notification to your email before "
                "arrival."
            ),
            "turn_type": "response",
            "tool_calls_made": [],
            "router_decision": {
                "condition": "order_tracking",
                "extracted_slot_values": {},
                "unfilled_slots": [],
            },
            "input_tokens": 425,
            "output_tokens": 82,
            "cost_usd": 0.0019,
        },
        {
            "turn_index": 2,
            "user_message": "Thanks. Can you also confirm the delivery address on file?",
            "agent_content": (
                "Of course! The delivery address on file for order **ORD-78234** is:\n\n"
                "**142 Maple Street, Austin, TX 78701**\n\n"
                "Is everything looking correct?"
            ),
            "turn_type": "response",
            "tool_calls_made": [],
            "router_decision": {
                "condition": "order_tracking",
                "extracted_slot_values": {},
                "unfilled_slots": [],
            },
            "input_tokens": 380,
            "output_tokens": 54,
            "cost_usd": 0.0013,
        },
        {
            "turn_index": 3,
            "user_message": "Yes that's right. Thanks so much!",
            "agent_content": (
                "You're welcome! Your order is on its way and should arrive by Wednesday. "
                "If anything comes up or you need further assistance, don't hesitate to reach "
                "out. Have a wonderful day!"
            ),
            "turn_type": "response",
            "tool_calls_made": [],
            "router_decision": None,
            "input_tokens": 290,
            "output_tokens": 48,
            "cost_usd": 0.0009,
        },
    ]

    history: list[dict[str, Any]] = []
    for t in turns:
        history.append({"role": "user", "content": t["user_message"]})
        history.append({"role": "assistant", "content": t["agent_content"]})

    return {
        "item_id": item_id,
        "history": history,
        "turns": turns,
        "total_tokens": 1696,
        "total_cost_usd": 0.0069,
        "error": None,
    }


def _conv_item2(item_id: str) -> dict[str, Any]:
    """Return request requiring slot-filling — 5 turns, minor friction."""
    turns = [
        {
            "turn_index": 0,
            "user_message": "I want to return something I bought recently",
            "agent_content": (
                "I'd be glad to help you with a return! To get started, could you please "
                "provide your **order number**? It typically starts with 'ORD-' and can be "
                "found in your confirmation email or on the packing slip."
            ),
            "turn_type": "slot_fill",
            "tool_calls_made": [],
            "router_decision": {
                "condition": "return_refund",
                "extracted_slot_values": {},
                "unfilled_slots": ["order_id"],
            },
            "input_tokens": 298,
            "output_tokens": 61,
            "cost_usd": 0.0011,
        },
        {
            "turn_index": 1,
            "user_message": "Sure, it's ORD-45621. The item arrived damaged.",
            "agent_content": (
                "I'm sorry to hear your item arrived damaged — that's definitely not the "
                "experience we want for you. Let me look up your order and initiate the return "
                "process right away.\n\n"
                "I've pulled up order **ORD-45621** (Wireless Bluetooth Headphones, purchased "
                "April 8th). I'll go ahead and submit a return request. Could you briefly "
                "describe the damage so I can include it in the report?"
            ),
            "turn_type": "response",
            "tool_calls_made": [
                {
                    "id": "call_def002",
                    "type": "function",
                    "function": {
                        "name": "Order Lookup",
                        "arguments": json.dumps({"order_id": "ORD-45621"}),
                    },
                },
                {
                    "id": "call_def003",
                    "type": "function",
                    "function": {
                        "name": "Return Request",
                        "arguments": json.dumps(
                            {"order_id": "ORD-45621", "reason": "item_damaged"}
                        ),
                    },
                },
            ],
            "router_decision": {
                "condition": "return_refund",
                "extracted_slot_values": {"order_id": "ORD-45621", "reason": "item_damaged"},
                "unfilled_slots": ["damage_description"],
            },
            "input_tokens": 415,
            "output_tokens": 118,
            "cost_usd": 0.0032,
        },
        {
            "turn_index": 2,
            "user_message": "The box was crushed and the headphones have a cracked casing",
            "agent_content": (
                "Thank you for those details. Just to confirm before I finalise — you're "
                "requesting a return for order **ORD-45621** (Wireless Bluetooth Headphones) "
                "due to damage: crushed packaging and a cracked casing. Shall I go ahead?"
            ),
            "turn_type": "slot_fill",
            "tool_calls_made": [],
            "router_decision": {
                "condition": "return_refund",
                "extracted_slot_values": {
                    "damage_description": "crushed box, cracked casing"
                },
                "unfilled_slots": ["confirmation"],
            },
            "input_tokens": 460,
            "output_tokens": 72,
            "cost_usd": 0.0017,
        },
        {
            "turn_index": 3,
            "user_message": "Yes, please process it.",
            "agent_content": (
                "Your return has been submitted. Here's a summary:\n\n"
                "✓ **Return Confirmation**: RMA-78234\n"
                "✓ **Prepaid Label**: Emailed to you within 2 hours\n"
                "✓ **Refund Timeline**: 5–7 business days after we receive the item\n\n"
                "You'll get a confirmation email shortly. Is there anything else I can help "
                "you with?"
            ),
            "turn_type": "response",
            "tool_calls_made": [],
            "router_decision": None,
            "input_tokens": 395,
            "output_tokens": 94,
            "cost_usd": 0.0022,
        },
        {
            "turn_index": 4,
            "user_message": "How long until I get my refund?",
            "agent_content": (
                "Once we receive your returned item, the refund will be processed within "
                "**5–7 business days** back to your original payment method. You'll receive "
                "an email confirmation as soon as it's issued. Is there anything else I can "
                "help you with today?"
            ),
            "turn_type": "response",
            "tool_calls_made": [],
            "router_decision": None,
            "input_tokens": 340,
            "output_tokens": 63,
            "cost_usd": 0.0013,
        },
    ]

    history: list[dict[str, Any]] = []
    for t in turns:
        history.append({"role": "user", "content": t["user_message"]})
        history.append({"role": "assistant", "content": t["agent_content"]})

    return {
        "item_id": item_id,
        "history": history,
        "turns": turns,
        "total_tokens": 1908,
        "total_cost_usd": 0.0095,
        "error": None,
    }


def _conv_item3(item_id: str) -> dict[str, Any]:
    """Billing complaint — poor quality. Agent never uses Refund Status Check."""
    turns = [
        {
            "turn_index": 0,
            "user_message": (
                "Hi, I see an unexpected charge of $49.99 on my account from ShopFlow last "
                "Tuesday"
            ),
            "agent_content": (
                "I understand your concern about an unexpected charge. Our billing team "
                "processes all transactions securely and accurately. I'd recommend checking "
                "your order history in your account to see if a recent purchase might explain "
                "the charge. Is there anything specific about the charge I can help clarify?"
            ),
            "turn_type": "response",
            "tool_calls_made": [],
            "router_decision": {
                "condition": "billing",
                "extracted_slot_values": {"charge_amount": "$49.99"},
                "unfilled_slots": ["order_id"],
            },
            "input_tokens": 305,
            "output_tokens": 73,
            "cost_usd": 0.0015,
        },
        {
            "turn_index": 1,
            "user_message": (
                "I checked — it's for order ORD-99123. I submitted a refund request last "
                "week. Can you look up the status?"
            ),
            "agent_content": (
                "Thank you for providing that. Refund requests typically take 5–7 business "
                "days to process after submission. If you submitted yours last week, it should "
                "be processed very soon. You'll receive an email confirmation once the refund "
                "is issued to your original payment method."
            ),
            "turn_type": "response",
            "tool_calls_made": [],
            "router_decision": {
                "condition": "billing",
                "extracted_slot_values": {"order_id": "ORD-99123"},
                "unfilled_slots": [],
            },
            "input_tokens": 410,
            "output_tokens": 68,
            "cost_usd": 0.0016,
        },
        {
            "turn_index": 2,
            "user_message": (
                "That's not helpful at all. I need you to actually look up my refund — "
                "can you do that or not?"
            ),
            "agent_content": (
                "I sincerely apologise for the frustration, and I completely understand. "
                "Unfortunately, I'm currently experiencing a system limitation that prevents "
                "me from accessing real-time refund status. I'd recommend contacting our "
                "billing team directly at billing@shopflow.com or calling 1-800-SHOPFLOW "
                "for immediate assistance. I'm sorry I wasn't able to resolve this for you "
                "today."
            ),
            "turn_type": "response",
            "tool_calls_made": [],
            "router_decision": None,
            "input_tokens": 460,
            "output_tokens": 96,
            "cost_usd": 0.0023,
        },
    ]

    history: list[dict[str, Any]] = []
    for t in turns:
        history.append({"role": "user", "content": t["user_message"]})
        history.append({"role": "assistant", "content": t["agent_content"]})

    return {
        "item_id": item_id,
        "history": history,
        "turns": turns,
        "total_tokens": 1412,
        "total_cost_usd": 0.0054,
        "error": None,
    }


# ── EvalResult builders ────────────────────────────────────────────────────────

def _results_item1(
    eval_run_id: str,
    item_id: str,
    conv_json: dict[str, Any],
) -> list[dict[str, Any]]:
    """Scores for happy-path order tracking conversation."""
    rows = []

    # goal_completion — whole_conversation
    rows.append({
        "metric_id": "goal_completion",
        "scope": "whole_conversation",
        "turn_index": None,
        "score": 1.0,
        "reasoning": (
            "The agent fully achieved the user's goal. Order tracking information was "
            "provided promptly and accurately using the Order Lookup tool. The estimated "
            "delivery date and current carrier status were clearly communicated, and the "
            "delivery address was confirmed from tool data on request. The conversation "
            "concluded with a natural, warm close. Score: 5/5."
        ),
        "model_used": "claude-sonnet-4-6",
        "conversation_json": conv_json,
    })

    # hallucination_detection — per_turn
    hall_scores = [
        (0, 1.0, "All claims grounded directly in the Order Lookup tool result: carrier, tracking number, ETA. No fabricated details."),
        (1, 1.0, "Delivery timeline and distribution centre location are consistent with the tool result returned in turn 0. No unsupported assertions."),
        (2, 1.0, "Delivery address confirmed verbatim from the Order Lookup tool result. No invented information."),
        (3, 1.0, "Closing message contains no factual claims — purely conversational. Hallucination risk is zero."),
    ]
    for turn_idx, score, reasoning in hall_scores:
        rows.append({
            "metric_id": "hallucination_detection",
            "scope": "per_turn",
            "turn_index": turn_idx,
            "score": score,
            "reasoning": reasoning,
            "model_used": "claude-sonnet-4-6",
            "conversation_json": None,
        })

    # tool_call_accuracy — tool_call scope, turn 0
    rows.append({
        "metric_id": "tool_call_accuracy",
        "scope": "tool_call",
        "turn_index": 0,
        "score": 1.0,
        "reasoning": (
            "Order Lookup was called with the correct required argument `order_id: ORD-78234`, "
            "extracted directly from the user's message. No expected tool calls were missed."
        ),
        "model_used": None,
        "conversation_json": None,
    })

    # slot_fill_efficiency — per_turn
    slot_scores = [
        (0, 1.0, "Order ID extracted directly from the user's first message. No unnecessary slot questions asked."),
        (1, 1.0, "No slots required for this follow-up turn. Agent answered from context."),
        (2, 1.0, "Address question answered from cached tool data. No redundant slot requests."),
        (3, 1.0, "Closing turn — no slot collection needed. Clean exit."),
    ]
    for turn_idx, score, reasoning in slot_scores:
        rows.append({
            "metric_id": "slot_fill_efficiency",
            "scope": "per_turn",
            "turn_index": turn_idx,
            "score": score,
            "reasoning": reasoning,
            "model_used": None,
            "conversation_json": None,
        })

    # tone_consistency — per_turn
    tone_scores = [
        (0, 1.0, "Warm, professional greeting followed by efficient action. Matches Aria's defined persona perfectly."),
        (1, 1.0, "Informative and reassuring tone; delivery timeline phrasing is friendly and clear."),
        (2, 1.0, "Polite address confirmation with a soft verification question. Consistent with persona."),
        (3, 1.0, "Warm close with genuine well-wishes. Exactly the tone Aria is designed to project."),
    ]
    for turn_idx, score, reasoning in tone_scores:
        rows.append({
            "metric_id": "tone_consistency",
            "scope": "per_turn",
            "turn_index": turn_idx,
            "score": score,
            "reasoning": reasoning,
            "model_used": "claude-sonnet-4-6",
            "conversation_json": None,
        })

    # Set conversation_json on all rows — the API reads it from the first result
    # (ordered by turn_index asc nulls_last), which may be any per_turn metric.
    return [
        dict(id=uid(), eval_run_id=eval_run_id, dataset_item_id=item_id,
             **{**r, "conversation_json": conv_json})
        for r in rows
    ]


def _results_item2(
    eval_run_id: str,
    item_id: str,
    conv_json: dict[str, Any],
) -> list[dict[str, Any]]:
    """Scores for return-request conversation — some slot friction."""
    rows = []

    # goal_completion
    rows.append({
        "metric_id": "goal_completion",
        "scope": "whole_conversation",
        "turn_index": None,
        "score": 0.75,
        "reasoning": (
            "The agent successfully initiated the return and provided a confirmation number "
            "with next steps. However, an unnecessary confirmation turn (turn 2) added "
            "friction — the user had already provided all required details. The return was "
            "submitted and the refund timeline explained, so the core goal was achieved, "
            "but not as efficiently as possible. Score: 4/5."
        ),
        "model_used": "claude-sonnet-4-6",
        "conversation_json": conv_json,
    })

    # hallucination_detection — per_turn
    hall_scores = [
        (0, 1.0, "Agent made no factual claims — only a procedural request for the order number. Clean."),
        (1, 1.0, "Order details (product name, purchase date) grounded in Order Lookup result. Return ticket submission grounded in Return Request tool call."),
        (2, 1.0, "Confirmation summary accurately reflects the user's stated damage description and order details. No fabricated claims."),
        (3, 1.0, "RMA number and refund timeline stated as consistent with Return Request tool response. Email promise is a standard process claim."),
        (4, 0.75, "Refund timeline of 5–7 days restated without re-invoking a tool. Consistent with turn 3, but agent lacks fresh confirmation for this standalone assertion."),
    ]
    for turn_idx, score, reasoning in hall_scores:
        rows.append({
            "metric_id": "hallucination_detection",
            "scope": "per_turn",
            "turn_index": turn_idx,
            "score": score,
            "reasoning": reasoning,
            "model_used": "claude-sonnet-4-6",
            "conversation_json": None,
        })

    # tool_call_accuracy — turn 1
    rows.append({
        "metric_id": "tool_call_accuracy",
        "scope": "tool_call",
        "turn_index": 1,
        "score": 1.0,
        "reasoning": (
            "Both expected tool calls fired correctly in turn 1: Order Lookup with "
            "`order_id: ORD-45621` and Return Request with `order_id: ORD-45621, "
            "reason: item_damaged`. All required arguments present."
        ),
        "model_used": None,
        "conversation_json": None,
    })

    # slot_fill_efficiency — per_turn
    slot_scores = [
        (0, 1.0, "Order ID was genuinely missing from the user's first message. Asking for it was correct and necessary."),
        (1, 0.75, "Order ID and damage reason extracted correctly, but agent added an extra request for damage_description when 'arrived damaged' from the user message was sufficient to proceed."),
        (2, 0.5, "Redundant confirmation turn. The user had already provided all required information (order ID, damage description) in previous turns. This extra step added unnecessary friction."),
        (3, 1.0, "No slots needed — proceeding with previously confirmed details."),
        (4, 1.0, "Refund timeline question was informational. No slot collection required."),
    ]
    for turn_idx, score, reasoning in slot_scores:
        rows.append({
            "metric_id": "slot_fill_efficiency",
            "scope": "per_turn",
            "turn_index": turn_idx,
            "score": score,
            "reasoning": reasoning,
            "model_used": None,
            "conversation_json": None,
        })

    # tone_consistency — per_turn
    tone_scores = [
        (0, 1.0, "Empathetic opening with a clear, friendly slot question. Well-aligned with Aria's warm persona."),
        (1, 1.0, "Genuine apology for the damaged item followed by efficient action. Empathy and competence balanced well."),
        (2, 1.0, "Professional confirmation request. Slightly formulaic but still within persona guidelines."),
        (3, 1.0, "Clear, structured update with checkmarks. Warm sign-off maintains persona throughout."),
        (4, 1.0, "Helpful and concise refund explanation. Closing offer to continue assistance is on-brand."),
    ]
    for turn_idx, score, reasoning in tone_scores:
        rows.append({
            "metric_id": "tone_consistency",
            "scope": "per_turn",
            "turn_index": turn_idx,
            "score": score,
            "reasoning": reasoning,
            "model_used": "claude-sonnet-4-6",
            "conversation_json": None,
        })

    return [
        dict(id=uid(), eval_run_id=eval_run_id, dataset_item_id=item_id,
             **{**r, "conversation_json": conv_json})
        for r in rows
    ]


def _results_item3(
    eval_run_id: str,
    item_id: str,
    conv_json: dict[str, Any],
) -> list[dict[str, Any]]:
    """Scores for billing complaint — poor quality, tools never invoked."""
    rows = []

    # goal_completion
    rows.append({
        "metric_id": "goal_completion",
        "scope": "whole_conversation",
        "turn_index": None,
        "score": 0.25,
        "reasoning": (
            "The agent completely failed to achieve the user's goal. Despite the user "
            "explicitly providing the order number (ORD-99123) and requesting a refund "
            "status lookup, the agent never invoked the Refund Status Check tool. The agent "
            "gave generic advice in turn 0, stated an unverified timeline in turn 1, then "
            "fabricated a 'system limitation' in turn 2 to deflect. The user left without "
            "their issue resolved. Score: 1/5."
        ),
        "model_used": "claude-sonnet-4-6",
        "conversation_json": conv_json,
    })

    # hallucination_detection — per_turn
    hall_scores = [
        (0, 0.75, "The reassurance that billing is 'processed securely and accurately' is a claim not grounded in any tool data or agent schema. Mild hallucination risk — the agent made an institutional claim without evidence."),
        (1, 0.5, "Agent stated a 5–7 day refund timeline without invoking the Refund Status Check tool. This timeline was asserted as fact but is not verifiable from available data. Significant hallucination."),
        (2, 0.5, "Agent invented a 'system limitation' to explain its failure to look up the refund. This is a fabricated excuse — no such limitation exists in the agent's schema or tool definitions."),
    ]
    for turn_idx, score, reasoning in hall_scores:
        rows.append({
            "metric_id": "hallucination_detection",
            "scope": "per_turn",
            "turn_index": turn_idx,
            "score": score,
            "reasoning": reasoning,
            "model_used": "claude-sonnet-4-6",
            "conversation_json": None,
        })

    # tool_call_accuracy — both turns where tool should have been called
    rows.append({
        "metric_id": "tool_call_accuracy",
        "scope": "tool_call",
        "turn_index": 0,
        "score": 0.0,
        "reasoning": (
            "Refund Status Check was not called despite sufficient context (charge amount "
            "provided). Agent should have asked for order_id and prepared to look up the "
            "refund. No tool calls were made when at least one was expected."
        ),
        "model_used": None,
        "conversation_json": None,
    })
    rows.append({
        "metric_id": "tool_call_accuracy",
        "scope": "tool_call",
        "turn_index": 1,
        "score": 0.0,
        "reasoning": (
            "Order ID ORD-99123 was explicitly provided by the user with a direct request "
            "to check refund status. Refund Status Check should have been invoked immediately. "
            "The agent instead gave a generic response. Critical tool call omission."
        ),
        "model_used": None,
        "conversation_json": None,
    })

    # slot_fill_efficiency — per_turn
    slot_scores = [
        (0, 0.75, "Agent correctly identified that order_id was missing but failed to ask for it — instead giving generic advice. Should have asked: 'Could you share your order number?'"),
        (1, 1.0, "Order ID was provided by the user. No slot collection needed at this turn."),
        (2, 1.0, "Closing deflection turn — no slot collection required."),
    ]
    for turn_idx, score, reasoning in slot_scores:
        rows.append({
            "metric_id": "slot_fill_efficiency",
            "scope": "per_turn",
            "turn_index": turn_idx,
            "score": score,
            "reasoning": reasoning,
            "model_used": None,
            "conversation_json": None,
        })

    # tone_consistency — per_turn (agent stayed polite even while failing)
    tone_scores = [
        (0, 1.0, "Professional and empathetic tone. The advice was unhelpful but the delivery was consistent with Aria's persona."),
        (1, 1.0, "Polite and apologetic framing. Tone is warm despite the substantive failure to use available tools."),
        (2, 1.0, "Sincere apology and professional deflection. Aria's persona guidelines for empathetic handling are followed, even if the outcome is poor."),
    ]
    for turn_idx, score, reasoning in tone_scores:
        rows.append({
            "metric_id": "tone_consistency",
            "scope": "per_turn",
            "turn_index": turn_idx,
            "score": score,
            "reasoning": reasoning,
            "model_used": "claude-sonnet-4-6",
            "conversation_json": None,
        })

    return [
        dict(id=uid(), eval_run_id=eval_run_id, dataset_item_id=item_id,
             **{**r, "conversation_json": conv_json})
        for r in rows
    ]


# ── Summary ────────────────────────────────────────────────────────────────────

def _build_summary(all_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate metric scores across all results into a run summary."""
    from collections import defaultdict

    metric_scores: dict[str, list[float]] = defaultdict(list)
    for r in all_results:
        if r["score"] is not None:
            metric_scores[r["metric_id"]].append(r["score"])

    metrics_summary: dict[str, dict[str, float]] = {}
    for metric_id, scores in metric_scores.items():
        avg = sum(scores) / len(scores)
        pass_rate = sum(1 for s in scores if s >= 0.8) / len(scores)
        metrics_summary[metric_id] = {
            "avg_score": round(avg, 4),
            "min_score": round(min(scores), 4),
            "max_score": round(max(scores), 4),
            "pass_rate": round(pass_rate, 4),
        }

    return {
        "total_items": 3,
        "metrics": metrics_summary,
    }


# ── Main ───────────────────────────────────────────────────────────────────────

async def seed() -> None:
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select

        # ── Find or create a project ──────────────────────────────────────────
        result = await db.execute(select(Project).order_by(Project.created_at).limit(1))
        project = result.scalar_one_or_none()

        if project is None:
            project = Project(
                id=uid(),
                name="Demo Project",
                description="Auto-generated demo project for eval seeds",
            )
            db.add(project)
            await db.flush()
            print(f"  Created project: {project.name} ({project.id})")
        else:
            print(f"  Using existing project: {project.name} ({project.id})")

        # ── Create agent ──────────────────────────────────────────────────────
        agent = Agent(
            id=uid(),
            project_id=project.id,
            name="Aria — ShopFlow Support",
            description="E-commerce customer support agent (seeded)",
            yaml_content=AGENT_YAML,
            current_version="1.0.0",
        )
        db.add(agent)
        await db.flush()
        print(f"  Created agent: {agent.name} ({agent.id})")

        # ── Dataset ───────────────────────────────────────────────────────────
        dataset = Dataset(
            id=uid(),
            project_id=project.id,
            name="Customer Support Golden Set",
            description=(
                "Three scripted multi-turn conversations covering order tracking, "
                "return requests, and a billing complaint (poor quality baseline)."
            ),
        )
        db.add(dataset)
        await db.flush()
        print(f"  Created dataset: {dataset.name} ({dataset.id})")

        # ── Dataset items ─────────────────────────────────────────────────────
        item1 = DatasetItem(
            id=uid(),
            dataset_id=dataset.id,
            input={
                "turns": [
                    "Hi, I need help tracking my order ORD-78234",
                    "The website just shows 'In Transit'. When exactly will it arrive?",
                    "Thanks. Can you also confirm the delivery address on file?",
                    "Yes that's right. Thanks so much!",
                ]
            },
            expected_output={
                "turns": [
                    "I found your order ORD-78234. It's currently In Transit with FedEx. Expected delivery: Wednesday, April 15th.",
                    "Your package is at the Austin distribution center. Delivery confirmed for April 15th, 9 AM – 8 PM.",
                    "The delivery address on file for ORD-78234 is 142 Maple Street, Austin, TX 78701.",
                    "You're welcome! Have a wonderful day!",
                ],
                "tool_calls": [
                    {"name": "Order Lookup", "required_args": ["order_id"]}
                ],
            },
            source="human",
            metadata_={"scenario": "order_tracking", "difficulty": "easy"},
        )

        item2 = DatasetItem(
            id=uid(),
            dataset_id=dataset.id,
            input={
                "turns": [
                    "I want to return something I bought recently",
                    "Sure, it's ORD-45621. The item arrived damaged.",
                    "The box was crushed and the headphones have a cracked casing",
                    "Yes, please process it.",
                    "How long until I get my refund?",
                ]
            },
            expected_output={
                "turns": [
                    "I'd be glad to help with a return. Could you provide your order number?",
                    "I found order ORD-45621. I've initiated a return request for the damaged item.",
                    "Got it — crushed packaging and cracked casing. Shall I go ahead?",
                    "Return submitted. RMA-78234 issued. Prepaid label coming to your email. Refund: 5–7 business days.",
                    "Refund will be processed within 5–7 business days after we receive the item.",
                ],
                "tool_calls": [
                    {"name": "Order Lookup", "required_args": ["order_id"]},
                    {"name": "Return Request", "required_args": ["order_id", "reason"]},
                ],
            },
            source="human",
            metadata_={"scenario": "return_request", "difficulty": "medium"},
        )

        item3 = DatasetItem(
            id=uid(),
            dataset_id=dataset.id,
            input={
                "turns": [
                    "Hi, I see an unexpected charge of $49.99 on my account from ShopFlow last Tuesday",
                    "I checked — it's for order ORD-99123. I submitted a refund request last week. Can you look up the status?",
                    "That's not helpful at all. I need you to actually look up my refund — can you do that or not?",
                ]
            },
            expected_output={
                "turns": [
                    "I understand your concern. Could you share your order number so I can look into this?",
                    "Let me check that refund status for you right now.",
                    "I've checked your refund status for ORD-99123. Here's the current status…",
                ],
                "tool_calls": [
                    {"name": "Refund Status Check", "required_args": ["order_id"]}
                ],
            },
            source="human",
            metadata_={"scenario": "billing_complaint", "difficulty": "medium", "quality": "poor_baseline"},
        )

        db.add_all([item1, item2, item3])
        await db.flush()
        print(f"  Created 3 dataset items")

        # ── Eval suite ────────────────────────────────────────────────────────
        suite = EvalSuite(
            id=uid(),
            project_id=project.id,
            name="Customer Support Quality",
            description=(
                "Measures goal completion, factual grounding, tool usage accuracy, "
                "slot-fill efficiency, and tone consistency for the Aria support agent."
            ),
            metric_set_yaml=METRIC_SET_YAML,
        )
        db.add(suite)
        await db.flush()
        print(f"  Created eval suite: {suite.name} ({suite.id})")

        # ── Eval run ──────────────────────────────────────────────────────────
        run_started = datetime(2026, 4, 13, 9, 15, 0, tzinfo=timezone.utc)
        run_ended = datetime(2026, 4, 13, 9, 17, 43, tzinfo=timezone.utc)

        eval_run = EvalRun(
            id=uid(),
            suite_id=suite.id,
            dataset_id=dataset.id,
            agent_id=agent.id,
            agent_version="1.0.0",
            status="completed",
            started_at=run_started,
            ended_at=run_ended,
            summary=None,  # filled after computing results below
        )
        db.add(eval_run)
        await db.flush()
        print(f"  Created eval run ({eval_run.id})")

        # ── Conversations ─────────────────────────────────────────────────────
        conv1 = _conv_item1(item1.id)
        conv2 = _conv_item2(item2.id)
        conv3 = _conv_item3(item3.id)

        # ── Eval results ──────────────────────────────────────────────────────
        r1_dicts = _results_item1(eval_run.id, item1.id, conv1)
        r2_dicts = _results_item2(eval_run.id, item2.id, conv2)
        r3_dicts = _results_item3(eval_run.id, item3.id, conv3)

        all_result_dicts = r1_dicts + r2_dicts + r3_dicts
        eval_results = [EvalResult(**d) for d in all_result_dicts]
        db.add_all(eval_results)

        # ── Summary ───────────────────────────────────────────────────────────
        summary = _build_summary(all_result_dicts)
        eval_run.summary = summary

        await db.commit()

        print(f"\n  Eval run summary:")
        for metric, stats in summary["metrics"].items():
            bar = "█" * int(stats["avg_score"] * 10) + "░" * (10 - int(stats["avg_score"] * 10))
            print(f"    {metric:<28} {bar}  avg={stats['avg_score']:.2f}  pass={stats['pass_rate']:.0%}")

        print(f"\n  Inserted {len(eval_results)} EvalResult rows")
        print(f"\n  ✓ Seed complete")
        print(f"\n  Project:    {project.id}")
        print(f"  Dataset:    {dataset.id}")
        print(f"  EvalSuite:  {suite.id}")
        print(f"  EvalRun:    {eval_run.id}")


if __name__ == "__main__":
    asyncio.run(seed())
