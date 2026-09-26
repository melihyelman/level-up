"""Follow-up Q&A about an assessed frame ("D6 neden kritik?", "R125'e güvenebilir miyiz?")."""
from __future__ import annotations

import json

from core.scene import Scene
from . import llm_client
from .prompts import CHAT_SYSTEM
from .tools import SCHEMAS, ToolBox

CHAT_TOOLS = [s for s in SCHEMAS if s["function"]["name"] != "submit_assessment"]
MAX_TOOL_ROUNDS = 4


def answer(question: str, assessment: dict, history: list[dict]) -> tuple[str, list[str]]:
    """assessment: output of runner.assess. Returns (answer text, tools used)."""
    if not llm_client.available():
        return "LLM erişimi yok (GLM_API_KEY tanımlı değil).", []
    usage = llm_client.Usage()
    tb = ToolBox(Scene(assessment["image_id"]))
    # the agent's own earlier tool results are its memory of this frame
    seen = [f"{ev['title']}: {ev['detail']}" for ev in assessment["trace"] if ev["kind"] == "tool_result"]
    ctx = (f"KARE: {assessment['image_id']}\nÖNCEKİ DEĞERLENDİRMEN:\n"
           f"{json.dumps(assessment['brief'], ensure_ascii=False)}\n\nO SIRADA ARAÇLARDAN ALDIĞIN VERİLER:\n" + "\n".join(seen))
    messages = [{"role": "system", "content": CHAT_SYSTEM},
                {"role": "user", "content": ctx},
                {"role": "assistant", "content": "Tamam, bu kareyle ilgili sorunuz nedir?"},
                *history[-8:],
                {"role": "user", "content": question}]
    used = []
    for rnd in range(MAX_TOOL_ROUNDS + 1):
        kw = {"tools": CHAT_TOOLS} if rnd < MAX_TOOL_ROUNDS else {}
        msg = llm_client.chat(messages, usage, effort="low", **kw).choices[0].message
        if not msg.tool_calls:
            return msg.content or "(boş cevap)", used
        messages.append({"role": "assistant", "content": msg.content or "",
                         "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
        imgs = []
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            used.append(tc.function.name)
            text, img = tb.call(tc.function.name, args)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": text})
            if img:
                imgs += [{"type": "text", "text": f"{tc.function.name} görüntüsü:"},
                         {"type": "image_url", "image_url": {"url": img}}]
        if imgs:
            messages.append({"role": "user", "content": imgs})
    return "Cevap üretilemedi.", used
