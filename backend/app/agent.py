import json
import re
from ollama import Client

from .config import OLLAMA_URL, OLLAMA_MODEL, TOP_K
from .mcp_client import MCPClientManager

TOOL_LABELS = {
    "vector_search": "RAG Search",
    "calculator": "Calculator",
    "python": "Python Interpreter Tool",
    "direct": "Direct Answer",
}

MCP_TOOL_NAMES = {
    "vector_search": "search_documentation",
    "calculator": "calculate_expression",
    "python": "execute_python_code",
}

ROUTER_SYSTEM = """You are the routing agent for a technical-document assistant.

Your job is to identify the BEST TOOL for the user's CURRENT REQUEST before answering.

Available tools:

1. python
Use the Python Interpreter Tool / Code Runner when the user asks to:
- write Python code
- generate Python code
- create a Python script
- implement something in Python
- solve a programming problem using Python
- show a Python example
- write a Python function
- write Python classes
- write Python automation code
- modify or debug Python code
- explain Python code with an example
- execute or calculate something using Python
- create code using asyncio, threading, multiprocessing, pandas, numpy, etc.
- produce a Python implementation based on a requirement

IMPORTANT:
If the user's main request is to WRITE or GENERATE PYTHON CODE,
choose python even if the topic is related to the Python documentation.

2. vector_search
Use RAG Search when the user asks for information that must be
retrieved from the supplied documents, for example:
- What does the Python documentation say about X?
- What does the AWS Well-Architected Framework say about X?
- What does NIST SP 800-145 define as X?
- Find a specific definition, rule, requirement, or fact in the documents.
- Questions requiring document citations.

If the user only wants Python code, do NOT choose vector_search.

3. calculator
Use Calculator for arithmetic or mathematical expressions, for example:
- 25 * 40
- 1250 * 0.18 + 47.5
- calculate a percentage
- perform a numerical calculation

4. direct
Use Direct Answer for:
- greetings
- casual conversation
- simple explanations that do not require document retrieval
- non-tool questions

IMPORTANT ROUTING RULES:

A. "Write Python code to..." -> python
B. "Give me a Python example for..." -> python
C. "Create a Python function that..." -> python
D. "Implement this in Python..." -> python
E. "Debug this Python code..." -> python
F. "How do I do X in Python? Show code." -> python
G. "According to the Python documentation, what is asyncio.TaskGroup?" -> vector_search
H. "What does the Python documentation say about asyncio.TaskGroup?" -> vector_search
I. "Look up asyncio.TaskGroup in the documentation and explain it." -> vector_search
J. "Look up asyncio.TaskGroup and then write Python code using it." -> python

Always prioritize the user's requested OUTPUT TYPE.
If the requested output is Python code, choose python.

Return ONLY valid JSON:
{
  "tool": "vector_search|calculator|python|direct",
  "input": "...",
  "reason": "short reason"
}

Never return markdown.
Never invent document facts.
"""

ANSWER_SYSTEM = """You are the final answer agent for a technical RAG assistant.
Use retrieved document context for document facts. Cite document claims inline as [Document, p. N].
Be clear and concise. If code is requested, give a minimal working example.
Do not claim a tool was used unless it actually ran.
"""

_mcp_manager = MCPClientManager()


def _client():
    return Client(host=OLLAMA_URL)


async def initialize_mcp():
    """Start MCP client sessions and dynamically discover server tools."""
    await _mcp_manager.initialize()


async def shutdown_mcp():
    """Close all MCP server sessions."""
    await _mcp_manager.close()


def get_mcp_tools():
    """Return the tool definitions discovered from connected MCP servers."""
    return _mcp_manager.tools


def is_python_code_request(query: str) -> bool:
    q = query.lower().strip()

    code_phrases = [
        "write python code", "write python program", "write python script",
        "write a python function", "write python function", "create python code",
        "create a python program", "create a python script", "generate python code",
        "generate a python program", "generate a python script", "implement in python",
        "implement this in python", "code in python", "python example",
        "python code example", "python implementation", "python program",
        "python script", "python function", "python class", "python code",
        "debug python", "modify python code", "fix python code", "execute python",
        "run python code",
    ]

    documentation_code_phrases = [
        "look up", "lookup", "according to the documentation",
        "python documentation", "python reference", "reference documentation",
    ]

    code_output_phrases = [
        "write", "create", "generate", "implement", "show",
        "give me", "provide", "build",
    ]

    if any(phrase in q for phrase in code_phrases):
        return True

    has_documentation_request = any(
        phrase in q for phrase in documentation_code_phrases
    )
    has_code_output_request = any(
        phrase in q for phrase in code_output_phrases
    )
    mentions_python = "python" in q or "asyncio" in q

    if has_documentation_request and has_code_output_request and mentions_python:
        return True

    python_concepts = [
        "asyncio", "taskgroup", "coroutine", "threading", "multiprocessing",
        "pandas", "numpy", "flask", "fastapi", "django", "pytest",
    ]
    has_python_concept = any(concept in q for concept in python_concepts)

    return has_python_concept and has_code_output_request


def route(query: str, history=None):
    if is_python_code_request(query):
        return {
            "tool": "python",
            "input": query,
            "reason": (
                "The user requested Python code as the primary output. "
                "Python Interpreter Tool has priority over documentation lookup."
            ),
        }

    client = _client()
    messages = [{"role": "system", "content": ROUTER_SYSTEM}]

    if history:
        for m in history[-6:]:
            if m.get("role") in ("user", "assistant"):
                messages.append({
                    "role": m["role"],
                    "content": str(m.get("content", "")),
                })

    messages.append({"role": "user", "content": query})

    response = client.chat(
        model=OLLAMA_MODEL,
        messages=messages,
        options={"temperature": 0},
    )

    content = response["message"]["content"].strip()
    match = re.search(r"\{.*\}", content, re.S)

    if not match:
        return {
            "tool": "vector_search",
            "input": query,
            "reason": "Document-first fallback",
        }

    try:
        data = json.loads(match.group(0))
        if data.get("tool") not in TOOL_LABELS:
            raise ValueError("Invalid tool selected")
        return data
    except Exception:
        return {
            "tool": "vector_search",
            "input": query,
            "reason": "Document-first fallback",
        }


def _structured_result(result):
    """Read structured MCP output across supported SDK naming conventions."""
    value = getattr(result, "structured_content", None)
    if value is None:
        value = getattr(result, "structuredContent", None)
    return value


def _text_result(result):
    parts = []
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def _normalize_rag_result(result):
    data = _structured_result(result)

    if isinstance(data, dict):
        rows = data.get("results", [])
        if isinstance(rows, list):
            return rows, data.get("message")

    text = _text_result(result)
    if text:
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed.get("results", []), parsed.get("message")
        except json.JSONDecodeError:
            pass

    return [], None


async def answer(query: str, history=None, selected_tool=None):
    plan = route(query, history) if not selected_tool else {
        "tool": selected_tool,
        "input": query,
        "reason": "Tool selected by the routing agent before execution",
    }

    tool = plan["tool"]
    tool_input = plan.get("input") or query
    steps = [f"Agent selected: {TOOL_LABELS[tool]} — {plan.get('reason', '')}"]
    citations = []

    if tool == "vector_search":
        mcp_name = MCP_TOOL_NAMES[tool]
        result = await _mcp_manager.call_tool(
            mcp_name,
            {"query": tool_input, "top_k": TOP_K},
        )
        rows, message = _normalize_rag_result(result)
        steps.append(
            f"MCP Client called '{mcp_name}' and RAG Search retrieved {len(rows)} document chunks."
        )
        if message:
            steps.append(message)

        citations = [
            {
                "document": r.get("source_doc", ""),
                "page": int(r.get("page_number", 0)),
                "section": r.get("section_heading") or None,
            }
            for r in rows
        ]
        context = "\n\n".join(
            f"[{r.get('source_doc', '')}, p. {r.get('page_number', 0)}]\n{r.get('text', '')}"
            for r in rows
        )
        prompt = (
            f"Question: {query}\n\n"
            f"Retrieved context:\n{context}\n\n"
            "Answer with citations."
        )

    elif tool == "calculator":
        mcp_name = MCP_TOOL_NAMES[tool]
        try:
            result = await _mcp_manager.call_tool(
                mcp_name,
                {"expression": tool_input},
            )
            value = _structured_result(result)
            if value is None:
                value = _text_result(result)
            steps.append(f"MCP Client called '{mcp_name}' for the numeric expression.")
        except Exception as e:
            value = f"Calculator error: {e}"
        prompt = f"Question: {query}\nCalculator result: {value}"

    elif tool == "python":
        mcp_name = MCP_TOOL_NAMES[tool]
        try:
            result = await _mcp_manager.call_tool(
                mcp_name,
                {"code": tool_input},
            )
            value = _structured_result(result)
            if value is None:
                value = _text_result(result)
            steps.append(f"MCP Client called '{mcp_name}' and executed the requested safe code.")
        except Exception as e:
            value = f"Python tool error: {e}"
        prompt = f"Question: {query}\nPython tool result: {value}"

    else:
        value = "No external tool required."
        steps.append("No external tool was required.")
        prompt = f"Question: {query}"

    client = _client()
    messages = [{"role": "system", "content": ANSWER_SYSTEM}]

    if history:
        for m in history[-6:]:
            if m.get("role") in ("user", "assistant"):
                messages.append({
                    "role": m["role"],
                    "content": str(m.get("content", "")),
                })

    messages.append({"role": "user", "content": prompt})

    response = client.chat(
        model=OLLAMA_MODEL,
        messages=messages,
        options={"temperature": 0.2},
    )
    final_answer = response["message"]["content"].strip()

    seen, unique = set(), []
    for citation in citations:
        key = (citation["document"], citation["page"])
        if key not in seen:
            seen.add(key)
            unique.append(citation)

    return {
        "answer": final_answer,
        "tool": tool,
        "tool_label": TOOL_LABELS[tool],
        "citations": unique,
        "steps": steps,
    }
