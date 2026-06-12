from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from langgraph.graph import END, START, StateGraph

from app.config import Settings
from app.prompts import (
    DATA_WORKER_PROMPT,
    POLICY_WORKER_PROMPT,
    RESPONSE_WORKER_PROMPT,
    SUPERVISOR_PROMPT,
)
from app.state import ShoppingState
from app.utils import dump_json, extract_json_payload, get_last_ai_content, list_worker_tools


class ShoppingAssistant:
    """Multi-agent shopping assistant backed by LangGraph."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.load()
        self._init_components()
        self.graph = self._build_graph()

    def _init_components(self) -> None:
        from app.data_access import ShoppingDataStore, build_data_tools
        from provider import get_chat_model
        from rag.embeddings import SentenceTransformerEmbeddings
        from rag.vector_store import ChromaPolicyStore

        self.llm = get_chat_model(self.settings)

        self.data_store = ShoppingDataStore(self.settings.orders_path)
        self.data_tools = build_data_tools(self.data_store)
        self.data_tools_map = {t.name: t for t in self.data_tools}

        self.embedding_model = SentenceTransformerEmbeddings(
            self.settings.embedding_model_name
        )
        self.vector_store = ChromaPolicyStore(
            persist_directory=self.settings.chroma_dir,
            embedding_model=self.embedding_model,
        )
        self.vector_store.ensure_index(self.settings.policy_path)

    def _build_graph(self) -> Any:
        llm = self.llm
        data_tools = self.data_tools
        data_tools_map = self.data_tools_map
        vector_store = self.vector_store
        top_k = self.settings.top_k

        def supervisor(state: ShoppingState) -> ShoppingState:
            return supervisor_node(state, llm)

        def worker_1(state: ShoppingState) -> ShoppingState:
            return worker_1_policy_node(state, llm, vector_store, top_k)

        def worker_2(state: ShoppingState) -> ShoppingState:
            return worker_2_data_node(state, llm, data_tools, data_tools_map)

        def worker_3(state: ShoppingState) -> ShoppingState:
            return worker_3_response_node(state, llm)

        graph = StateGraph(ShoppingState)
        graph.add_node("supervisor", supervisor)
        graph.add_node("worker_1_policy", worker_1)
        graph.add_node("worker_2_data", worker_2)
        graph.add_node("worker_3_response", worker_3)

        graph.add_edge(START, "supervisor")

        graph.add_conditional_edges(
            "supervisor",
            _route_after_supervisor,
            {
                "worker_1_policy": "worker_1_policy",
                "worker_2_data": "worker_2_data",
                "worker_3_response": "worker_3_response",
            },
        )

        graph.add_conditional_edges(
            "worker_1_policy",
            _route_after_policy,
            {
                "worker_2_data": "worker_2_data",
                "worker_3_response": "worker_3_response",
            },
        )

        graph.add_edge("worker_2_data", "worker_3_response")
        graph.add_edge("worker_3_response", END)

        return graph.compile()

    def ask(
        self,
        question: str,
        trace_file: Path | None = None,
        rebuild_index: bool = False,
    ) -> dict[str, Any]:
        if rebuild_index:
            self.vector_store.rebuild(self.settings.policy_path)

        initial_state: ShoppingState = {
            "question": question,
            "trace": [],
        }

        result = self.graph.invoke(initial_state)

        if trace_file:
            trace_path = Path(trace_file)
            trace_path.parent.mkdir(parents=True, exist_ok=True)
            trace_path.write_text(
                dump_json(result.get("trace", [])), encoding="utf-8"
            )

        return dict(result)

    def run_batch(
        self,
        test_file: Path,
        output_dir: Path,
        rebuild_index: bool = False,
    ) -> dict[str, Any]:
        if rebuild_index:
            self.vector_store.rebuild(self.settings.policy_path)

        cases: list[dict] = json.loads(
            Path(test_file).read_text(encoding="utf-8")
        )
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        results = []
        for case in cases:
            case_id = case.get("id", "unknown")
            question = case.get("question", "")
            expected_route: list[str] = case.get("expected_route", [])
            expected_status: str = case.get("expected_status", "ok")

            trace_path = output_dir / f"trace_{case_id}.json"
            result = self.ask(question, trace_file=trace_path)

            route = result.get("route") or {}
            actual_route: list[str] = []
            if route.get("status") == "clarification_needed":
                actual_route = ["clarification"]
            else:
                if route.get("needs_policy"):
                    actual_route.append("policy")
                if route.get("needs_data"):
                    actual_route.append("data")

            final_answer = result.get("final_answer", "")
            if "clarification_needed" in final_answer:
                actual_status = "clarification_needed"
            elif "not_found" in final_answer.lower():
                actual_status = "not_found"
            else:
                actual_status = "ok"

            # expected_route=[] means clarification path (no workers); treat as equivalent
            is_clarification_route = not expected_route and actual_route == ["clarification"]
            route_correct = is_clarification_route or sorted(expected_route) == sorted(actual_route)

            case_result = {
                "id": case_id,
                "question": question,
                "expected_route": expected_route,
                "actual_route": actual_route,
                "route_correct": route_correct,
                "expected_status": expected_status,
                "actual_status": actual_status,
                "status_correct": expected_status == actual_status,
                "final_answer": final_answer,
                "trace_file": str(trace_path),
            }
            results.append(case_result)

            route_mark = "✓" if case_result["route_correct"] else "✗"
            status_mark = "✓" if case_result["status_correct"] else "✗"
            print(f"[{case_id}] route={route_mark} status={status_mark}  {question[:60]}")

        total = len(results)
        route_ok = sum(1 for r in results if r["route_correct"])
        status_ok = sum(1 for r in results if r["status_correct"])

        summary = {
            "total": total,
            "route_correct": route_ok,
            "route_accuracy": round(route_ok / total, 3) if total else 0,
            "status_correct": status_ok,
            "status_accuracy": round(status_ok / total, 3) if total else 0,
            "cases": results,
        }

        summary_path = output_dir / "summary.json"
        summary_path.write_text(
            dump_json(summary), encoding="utf-8"
        )
        print(f"\nSummary saved to {summary_path}")
        return summary


# ── Routing helpers ──────────────────────────────────────────────────────────

def _route_after_supervisor(state: ShoppingState) -> str:
    route = state.get("route") or {}
    if route.get("status") == "clarification_needed":
        return "worker_3_response"
    if route.get("needs_policy"):
        return "worker_1_policy"
    if route.get("needs_data"):
        return "worker_2_data"
    return "worker_3_response"


def _route_after_policy(state: ShoppingState) -> str:
    route = state.get("route") or {}
    if route.get("needs_data"):
        return "worker_2_data"
    return "worker_3_response"


# ── Node implementations ─────────────────────────────────────────────────────

def supervisor_node(state: ShoppingState, llm: Any) -> ShoppingState:
    question = state["question"]
    messages = [
        SystemMessage(content=SUPERVISOR_PROMPT),
        HumanMessage(content=question),
    ]
    response = llm.invoke(messages)
    route = extract_json_payload(response.content)

    if not route:
        route = {
            "status": "ok",
            "needs_policy": True,
            "needs_data": False,
            "clarification_question": None,
        }

    return {
        "route": route,
        "trace": [{"node": "supervisor", "question": question, "route": route}],
    }


def worker_1_policy_node(
    state: ShoppingState,
    llm: Any,
    vector_store: Any,
    top_k: int,
) -> ShoppingState:
    question = state["question"]
    chunks = vector_store.search(question, top_k=top_k)

    context = "\n\n---\n\n".join(
        f"[{c['citation']}]\n{c['content']}" for c in chunks
    )

    messages = [
        SystemMessage(content=POLICY_WORKER_PROMPT),
        HumanMessage(content=f"Câu hỏi: {question}\n\nChính sách truy xuất:\n{context}"),
    ]
    response = llm.invoke(messages)
    policy_result = extract_json_payload(response.content)

    if not policy_result:
        policy_result = {
            "status": "ok",
            "summary": response.content,
            "facts": [],
            "citations": [],
        }

    policy_result["chunks"] = [
        {"citation": c["citation"], "distance": c["distance"]} for c in chunks
    ]

    return {
        "policy_result": policy_result,
        "trace": [
            {
                "node": "worker_1_policy",
                "chunks_retrieved": len(chunks),
                "citations": [c["citation"] for c in chunks],
                "policy_result": {k: v for k, v in policy_result.items() if k != "chunks"},
            }
        ],
    }


def worker_2_data_node(
    state: ShoppingState,
    llm: Any,
    data_tools: list,
    data_tools_map: dict,
) -> ShoppingState:
    question = state["question"]
    llm_with_tools = llm.bind_tools(data_tools)

    final_content, messages = _run_tool_calling_loop(
        llm_with_tools,
        data_tools_map,
        DATA_WORKER_PROMPT,
        question,
    )

    data_result = extract_json_payload(final_content)
    if not data_result:
        data_result = {
            "status": "ok",
            "summary": final_content,
            "facts": [],
            "missing_fields": [],
            "not_found_entities": [],
        }

    tool_calls_used = list_worker_tools(messages)

    return {
        "data_result": data_result,
        "trace": [
            {
                "node": "worker_2_data",
                "tool_calls": tool_calls_used,
                "data_result": data_result,
            }
        ],
    }


def worker_3_response_node(state: ShoppingState, llm: Any) -> ShoppingState:
    question = state["question"]
    route = state.get("route") or {}
    policy_result = state.get("policy_result") or {}
    data_result = state.get("data_result") or {}

    if route.get("status") == "clarification_needed":
        clarification_q = (
            route.get("clarification_question")
            or "Bạn có thể cung cấp thêm thông tin (mã đơn hàng hoặc mã khách hàng) không?"
        )
        final_answer = f"Status: clarification_needed\nQuestion: {clarification_q}"
        return {
            "final_answer": final_answer,
            "trace": [{"node": "worker_3_response", "status": "clarification_needed"}],
        }

    parts = [f"Câu hỏi của người dùng: {question}"]
    if policy_result:
        parts.append(
            f"Kết quả Policy Worker:\n{json.dumps(policy_result, ensure_ascii=False, indent=2)}"
        )
    if data_result:
        parts.append(
            f"Kết quả Data Worker:\n{json.dumps(data_result, ensure_ascii=False, indent=2)}"
        )

    messages = [
        SystemMessage(content=RESPONSE_WORKER_PROMPT),
        HumanMessage(content="\n\n".join(parts)),
    ]
    response = llm.invoke(messages)
    final_answer = response.content.strip()

    return {
        "final_answer": final_answer,
        "trace": [{"node": "worker_3_response", "final_answer": final_answer}],
    }


# ── Tool-calling loop ────────────────────────────────────────────────────────

def _run_tool_calling_loop(
    llm_with_tools: Any,
    tools_map: dict,
    system_prompt: str,
    question: str,
    max_iterations: int = 6,
) -> tuple[str, list]:
    messages: list = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=question),
    ]

    for _ in range(max_iterations):
        response = llm_with_tools.invoke(messages)
        messages.append(response)

        if not response.tool_calls:
            break

        for tool_call in response.tool_calls:
            tool_name = tool_call.get("name", "")
            tool_args = tool_call.get("args", {})
            tool_call_id = tool_call.get("id", "tool-call-0")

            tool_fn = tools_map.get(tool_name)
            if tool_fn:
                try:
                    raw = tool_fn.invoke(tool_args)
                    result_str = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
                except Exception as exc:
                    result_str = json.dumps({"error": str(exc)}, ensure_ascii=False)
            else:
                result_str = json.dumps(
                    {"error": f"Unknown tool: {tool_name}"}, ensure_ascii=False
                )

            messages.append(
                ToolMessage(content=result_str, tool_call_id=tool_call_id)
            )

    return get_last_ai_content(messages), messages


# ── Legacy standalone functions (kept for backward compat) ───────────────────

def build_graph() -> Any:
    return ShoppingAssistant()._build_graph()


def supervisor_node_standalone(state: ShoppingState) -> ShoppingState:  # type: ignore[return]
    raise NotImplementedError("Use ShoppingAssistant directly")


def worker_1_policy_node_standalone(state: ShoppingState) -> ShoppingState:  # type: ignore[return]
    raise NotImplementedError("Use ShoppingAssistant directly")


def worker_2_data_node_standalone(state: ShoppingState) -> ShoppingState:  # type: ignore[return]
    raise NotImplementedError("Use ShoppingAssistant directly")


def worker_3_response_node_standalone(state: ShoppingState) -> ShoppingState:  # type: ignore[return]
    raise NotImplementedError("Use ShoppingAssistant directly")
