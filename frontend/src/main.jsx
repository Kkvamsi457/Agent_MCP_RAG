import React, { useEffect, useMemo, useRef, useState } from "react";

import {
  Bot,
  Calculator,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Code2,
  Copy,
  FileText,
  Menu,
  MessageSquare,
  MoreHorizontal,
  Pencil,
  Plus,
  Search,
  Send,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";

import { createRoot } from "react-dom/client";

import "./styles.css";

const API = "http://127.0.0.1:8000";

const HISTORY_KEY = "atlas-agentic-rag-history-v3";

const ACTIVE_CHAT_KEY = "atlas-agentic-rag-active-chat-v1";

const NEW_CHAT_STATE = "__new_chat__";

const examples = [
  "What are the 6 pillars of the AWS Well-Architected Framework, and which pillar covers incident response?",

  "Look up the asyncio.TaskGroup class in the Python reference documentation and write a minimal code example showing two tasks concurrently.",

  "Using NIST SP 800-145, define the essential characteristics of cloud computing and state if on-demand self-service requires human interaction.",

  "Calculate (1250 \* 0.18) + 47.5.",
];

const toolMeta = {
  vector_search: { label: "RAG Search", icon: Search, className: "rag" },

  calculator: { label: "Calculator", icon: Calculator, className: "calc" },

  python: {
    label: "Python Interpreter Tool",

    icon: Code2,

    className: "python",
  },

  direct: { label: "Direct Answer", icon: Bot, className: "direct" },
};

function makeId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function loadHistory() {
  try {
    const value = JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");

    return Array.isArray(value) ? value : [];
  } catch {
    return [];
  }
}

function titleFrom(text) {
  const clean = text.replace(/\s+/g, " ").trim();

  return clean.length > 48 ? `${clean.slice(0, 48)}…` : clean || "New chat";
}

function App() {
  const [history, setHistory] = useState(loadHistory);

  const [activeId, setActiveId] = useState(null);

  const [input, setInput] = useState("");

  const [busy, setBusy] = useState(false);

  const [workingLabel, setWorkingLabel] = useState(
    "Agent is deciding which tool to use...",
  );

  const [sidebarOpen, setSidebarOpen] = useState(true);

  const [menuId, setMenuId] = useState(null);

  const [renamingId, setRenamingId] = useState(null);

  const [renameValue, setRenameValue] = useState("");

  const chatRef = useRef(null);

  const activeChat = useMemo(
    () => history.find((chat) => chat.id === activeId) || null,

    [history, activeId],
  );

  const messages = activeChat?.messages || [];

  useEffect(() => {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
  }, [history]);

  // Persist which conversation is open, including the explicit New Chat state.

  // This prevents a refresh from automatically reopening the previous chat.

  useEffect(() => {
    try {
      localStorage.setItem(ACTIVE_CHAT_KEY, activeId || NEW_CHAT_STATE);
    } catch {
      // Ignore storage errors (for example, private browsing restrictions).
    }
  }, [activeId]);

  // If a previously selected chat was removed outside this component, recover

  // gracefully. Do not select the first chat when the persisted state is New Chat.

  useEffect(() => {
    if (!activeId) return;

    const exists = history.some((chat) => chat.id === activeId);

    if (!exists) {
      setActiveId(null);
    }
  }, [history, activeId]);

  useEffect(() => {
    const el = chatRef.current;

    if (!el) return;

    // A new/empty chat must always start at the top of the landing page.

    // Existing conversations continue to auto-scroll to the newest message.

    if (messages.length === 0) {
      el.scrollTop = 0;
    } else {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages.length, busy, activeId]);

  const createChat = () => {
    // IMPORTANT: activeId=null is the explicit New Chat state.

    // We intentionally do not create an empty chat object in history.

    // A chat is created only when the user sends the first message.

    setActiveId(null);

    setInput("");

    setBusy(false);

    setMenuId(null);

    setRenamingId(null);

    // Cancel any pending browser scroll and force the empty/new-chat

    // landing view to the top.

    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (chatRef.current) {
          chatRef.current.scrollTo({ top: 0, left: 0, behavior: "auto" });
        }
      });
    });

    if (window.innerWidth < 900) setSidebarOpen(false);
  };

  const updateActiveMessages = (nextMessages) => {
    if (!activeId) return;

    setHistory((prev) =>
      prev.map((chat) =>
        chat.id === activeId
          ? { ...chat, messages: nextMessages, updatedAt: Date.now() }
          : chat,
      ),
    );
  };

  const send = async (text = input) => {
    text = text.trim();

    if (!text || busy) return;

    let chatId = activeId;

    let baseMessages = messages;

    if (!chatId) {
      chatId = makeId();

      baseMessages = [];

      const newChat = {
        id: chatId,

        title: titleFrom(text),

        messages: [],

        createdAt: Date.now(),

        updatedAt: Date.now(),
      };

      setHistory((prev) => [newChat, ...prev]);

      setActiveId(chatId);

      try {
        localStorage.setItem(ACTIVE_CHAT_KEY, chatId);
      } catch {}
    } else if (messages.length === 0) {
      setHistory((prev) =>
        prev.map((chat) =>
          chat.id === chatId
            ? { ...chat, title: titleFrom(text), updatedAt: Date.now() }
            : chat,
        ),
      );
    }

    const userMessage = { role: "user", content: text, id: makeId() };

    const nextMessages = [...baseMessages, userMessage];

    setHistory((prev) =>
      prev.map((chat) =>
        chat.id === chatId
          ? { ...chat, messages: nextMessages, updatedAt: Date.now() }
          : chat,
      ),
    );

    setInput("");

    setWorkingLabel("Agent is deciding which tool to use...");
    setBusy(true);

    setMenuId(null);

    const apiHistory = baseMessages.map((m) => ({
      role: m.role,

      content: m.content || m.answer || "",
    }));

    try {
      const routeResponse = await fetch(`${API}/api/route`, {
        method: "POST",

        headers: { "Content-Type": "application/json" },

        body: JSON.stringify({ message: text, history: apiHistory }),
      });

      const plan = await routeResponse.json();

      if (!routeResponse.ok) throw new Error(plan.detail || "Routing failed");

      const selectedTool = plan.tool;

      const selectedLabel =
        plan.tool_label ||
        toolMeta[selectedTool]?.label ||
        selectedTool ||
        "Direct Answer";

      setWorkingLabel(`Using ${selectedLabel}...`);

      const response = await fetch(`${API}/api/chat`, {
        method: "POST",

        headers: { "Content-Type": "application/json" },

        body: JSON.stringify({
          message: text,

          history: apiHistory,

          selected_tool: plan.tool,
        }),
      });

      const data = await response.json();

      if (!response.ok) throw new Error(data.detail || "Request failed");

      const assistantMessage = { role: "assistant", ...data, id: makeId() };

      setHistory((prev) =>
        prev.map((chat) =>
          chat.id === chatId
            ? {
                ...chat,

                messages: [...chat.messages, assistantMessage],

                updatedAt: Date.now(),
              }
            : chat,
        ),
      );
    } catch (error) {
      const errorMessage = {
        role: "assistant",

        content: `Something went wrong: ${error.message}`,

        tool: "direct",

        tool_label: "Direct Answer",

        citations: [],

        steps: [],

        id: makeId(),
      };

      setHistory((prev) =>
        prev.map((chat) =>
          chat.id === chatId
            ? {
                ...chat,

                messages: [...chat.messages, errorMessage],

                updatedAt: Date.now(),
              }
            : chat,
        ),
      );
    } finally {
      setBusy(false);
    }
  };

  const deleteChat = (id) => {
    setHistory((prev) => prev.filter((chat) => chat.id !== id));

    setMenuId(null);

    if (activeId === id) {
      const remaining = history.filter((chat) => chat.id !== id);

      const nextId = remaining[0]?.id || null;

      setActiveId(nextId);

      try {
        localStorage.setItem(ACTIVE_CHAT_KEY, nextId || NEW_CHAT_STATE);
      } catch {}
    }
  };

  const clearAll = () => {
    if (!history.length) return;

    if (!window.confirm("Clear all chat history? This cannot be undone."))
      return;

    setHistory([]);

    setActiveId(null);

    try {
      localStorage.setItem(ACTIVE_CHAT_KEY, NEW_CHAT_STATE);
    } catch {}

    setMenuId(null);
  };

  const startRename = (chat) => {
    setRenamingId(chat.id);

    setRenameValue(chat.title);

    setMenuId(null);
  };

  const saveRename = () => {
    if (!renamingId) return;

    const value = renameValue.trim();

    if (value) {
      setHistory((prev) =>
        prev.map((chat) =>
          chat.id === renamingId
            ? { ...chat, title: value, updatedAt: Date.now() }
            : chat,
        ),
      );
    }

    setRenamingId(null);
  };

  return (
    <div className="app-shell">
      <aside className={`sidebar ${sidebarOpen ? "open" : "closed"}`}>
        <div className="sidebar-header">
          <div className="brand">
            <div className="brandmark">
              <Sparkles size={19} />
            </div>

            <div>
              <strong>Atlas</strong>

              <span>Agentic RAG</span>
            </div>
          </div>

          <button
            className="mobile-close"
            onClick={() => setSidebarOpen(false)}
            aria-label="Close sidebar"
          >
            <X size={18} />
          </button>
        </div>

        <button className="new-chat" onClick={createChat}>
          <Plus size={17} />

          <span>New chat</span>

          <kbd>Ctrl K</kbd>
        </button>

        <div className="history-area">
          <div className="section-heading">
            <span>Chat history</span>

            <span className="history-count">{history.length}</span>
          </div>

          <div className="history-list">
            {history.length === 0 ? (
              <div className="history-empty">
                <MessageSquare size={19} />

                <p>No conversations yet.</p>

                <span>Your chats will appear here.</span>
              </div>
            ) : (
              history.map((chat) => (
                <div
                  key={chat.id}
                  className={`history-item ${chat.id === activeId ? "active" : ""}`}
                  onClick={() => {
                    setActiveId(chat.id);

                    try {
                      localStorage.setItem(ACTIVE_CHAT_KEY, chat.id);
                    } catch {}

                    setMenuId(null);

                    if (window.innerWidth < 900) setSidebarOpen(false);
                  }}
                >
                  <MessageSquare size={16} />

                  {renamingId === chat.id ? (
                    <input
                      autoFocus
                      className="rename-input"
                      value={renameValue}
                      onChange={(e) => setRenameValue(e.target.value)}
                      onClick={(e) => e.stopPropagation()}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") saveRename();

                        if (e.key === "Escape") setRenamingId(null);
                      }}
                      onBlur={saveRename}
                    />
                  ) : (
                    <span className="history-title">{chat.title}</span>
                  )}

                  <button
                    className="history-menu"
                    onClick={(e) => {
                      e.stopPropagation();

                      setMenuId(menuId === chat.id ? null : chat.id);
                    }}
                    aria-label="Chat options"
                  >
                    <MoreHorizontal size={16} />
                  </button>

                  {menuId === chat.id && (
                    <div
                      className="chat-menu"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <button onClick={() => startRename(chat)}>
                        <Pencil size={14} /> Rename
                      </button>

                      <button
                        className="danger"
                        onClick={() => deleteChat(chat.id)}
                      >
                        <Trash2 size={14} /> Delete
                      </button>
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>

        <div className="sidebar-footer">
          <button
            className="clear-history"
            onClick={clearAll}
            disabled={!history.length}
          >
            <Trash2 size={15} />

            <span>Clear all history</span>
          </button>

          <div className="sidebar-note">
            Your conversations are saved locally in this browser.
          </div>
        </div>
      </aside>

      {sidebarOpen && (
        <div className="mobile-overlay" onClick={() => setSidebarOpen(false)} />
      )}

      <main className="main-panel">
        <header className="topbar">
          <button
            className="icon-button"
            onClick={() => setSidebarOpen(!sidebarOpen)}
            aria-label="Toggle sidebar"
          >
            {sidebarOpen ? <ChevronLeft size={20} /> : <Menu size={20} />}
          </button>

          <div className="top-title">
            <span className="online-dot" />

            <span>Technical Assistant</span>
          </div>
        </header>

        <section className="chat-scroll" ref={chatRef}>
          {messages.length === 0 ? (
            <LandingPage onExample={send} />
          ) : (
            <div className="conversation">
              {messages.map((message) => (
                <Message
                  key={message.id || `${message.role}-${Math.random()}`}
                  message={message}
                />
              ))}

              {busy && <WorkingIndicator label={workingLabel} />}
            </div>
          )}
        </section>

        <div className="composer-area">
          <div className="composer">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();

                  send();
                }
              }}
              placeholder="Ask about Python, AWS, NIST, or calculate something..."
              rows="1"
              disabled={busy}
            />

            <button
              className="send-button"
              disabled={busy || !input.trim()}
              onClick={() => send()}
              aria-label="Send message"
            >
              <Send size={17} />
            </button>
          </div>

          <div className="composer-hint">
            Enter to send · Shift + Enter for a new line · Agent routing happens
            automatically
          </div>
        </div>
      </main>
    </div>
  );
}

function LandingPage({ onExample }) {
  return (
    <div className="landing">
      <div className="landing-glow glow-one" />

      <div className="landing-glow glow-two" />

      <div className="hero-logo">
        <Sparkles size={27} />
      </div>

      <div className="eyebrow">AGENTIC RAG · MULTI-TOOL ASSISTANT</div>

      <h1>
        Intelligent answers,
        <br />
        <span>grounded in your documents.</span>
      </h1>

      <p className="hero-copy">
        Atlas routes every request to the right tool — RAG Search, Python
        Interpreter, Calculator, or Direct Answer — then presents the result
        with clear sources.
      </p>

      <div className="tool-strip">
        <ToolMini icon={<Search size={15} />} label="RAG Search" color="blue" />

        <ToolMini
          icon={<Code2 size={15} />}
          label="Python Interpreter"
          color="green"
        />

        <ToolMini
          icon={<Calculator size={15} />}
          label="Calculator"
          color="purple"
        />

        <ToolMini icon={<Bot size={15} />} label="Direct Answer" color="gray" />
      </div>

      <div className="example-heading">Try an example</div>

      <div className="example-grid">
        {examples.map((example, index) => (
          <button
            className="example-card"
            key={index}
            onClick={() => onExample(example)}
          >
            <span>{example}</span>

            <ChevronRight size={16} />
          </button>
        ))}
      </div>
    </div>
  );
}

function ToolMini({ icon, label, color }) {
  return (
    <div className={`tool-mini ${color}`}>
      {icon}

      <span>{label}</span>
    </div>
  );
}

function WorkingIndicator({ label }) {
  return (
    <div className="working-row">
      <div className="assistant-avatar working-avatar">
        <Bot size={16} />
      </div>

      <div className="working-card">
        <div className="working-dots">
          <i />

          <i />

          <i />
        </div>

        <span>{label}</span>
      </div>
    </div>
  );
}

function Message({ message }) {
  if (message.role === "user") {
    return (
      <div className="message-row user-message-row">
        <div className="user-bubble">{message.content}</div>
      </div>
    );
  }

  const meta = toolMeta[message.tool] || toolMeta.direct;

  const Icon = meta.icon;

  const answer = message.answer || message.content || "";

  return (
    <div className="message-row assistant-row">
      <div className="assistant-avatar">
        <Bot size={17} />
      </div>

      <div className="assistant-content">
        <div className={`tool-chip ${meta.className}`}>
          <Icon size={14} />

          <span>{message.tool_label || meta.label}</span>

          <span className="tool-check">
            <Check size={11} />
          </span>
        </div>

        <div className="route-line">
          <span className="route-agent">Agent</span>

          <span>→</span>

          <strong>{message.tool_label || meta.label}</strong>

          <span>→</span>

          <span>Answer</span>
        </div>

        {message.steps?.map((step, index) => (
          <div className="step" key={index}>
            ✓ {step}
          </div>
        ))}

        <div className="answer-card">
          <RichAnswer text={answer} />

          <div className="answer-actions">
            <CopyButton text={answer} />
          </div>
        </div>

        {message.citations?.length > 0 && (
          <div className="citations">
            <div className="citations-title">
              <FileText size={13} /> Sources
            </div>

            <div className="citation-list">
              {message.citations.map((citation, index) => (
                <div
                  className="citation"
                  key={`${citation.document}-${citation.page}-${index}`}
                >
                  <FileText size={13} />

                  <span>{citation.document}</span>

                  <b>p. {citation.page}</b>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);

      setCopied(true);

      setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  };

  return (
    <button className="copy-answer" onClick={copy} title="Copy answer">
      {copied ? <Check size={14} /> : <Copy size={14} />}

      <span>{copied ? "Copied" : "Copy"}</span>
    </button>
  );
}

function RichAnswer({ text }) {
  const parts = text.split(/(```[\s\S]\\\*?```)/g);

  return (
    <div className="rich-answer">
      {parts.map((part, index) => {
        if (!part.startsWith("```")) {
          return <TextBlock key={index} text={part} />;
        }

        const lines = part

          .replace(/^```/, "")

          .replace(/```$/, "")

          .replace(/^\n/, "")

          .split("\n");

        const language = lines[0]?.trim() || "code";

        const code = lines.slice(1).join("\n");

        return <CodeBlock key={index} language={language} code={code} />;
      })}
    </div>
  );
}

function TextBlock({ text }) {
  if (!text.trim()) return null;

  const lines = text.split("\n");

  return (
    <div className="text-block">
      {lines.map((line, index) => {
        const trimmed = line.trim();

        if (trimmed.startsWith("### "))
          return <h4 key={index}>{trimmed.slice(4)}</h4>;

        if (trimmed.startsWith("## "))
          return <h3 key={index}>{trimmed.slice(3)}</h3>;

        if (trimmed.startsWith("# "))
          return <h2 key={index}>{trimmed.slice(2)}</h2>;

        if (/^[-\\\*]\s+/.test(trimmed))
          return (
            <div className="answer-list" key={index}>
              <span>•</span>

              {trimmed.replace(/^[-\\\*]\s+/, "")}
            </div>
          );

        if (/^\d+\.\s+/.test(trimmed))
          return (
            <div className="answer-list" key={index}>
              <span>{trimmed.match(/^\d+/)[0]}.</span>

              {trimmed.replace(/^\d+\.\s+/, "")}
            </div>
          );

        return <p key={index}>{formatInline(line)}</p>;
      })}
    </div>
  );
}

function formatInline(text) {
  const pieces = text.split(
    /(`[^`]+`|\\\\\\\*\\\\\\\*[^\\\*]+\\\\\\\*\\\\\\\*)/g,
  );

  return pieces.map((piece, index) => {
    if (piece.startsWith("`") && piece.endsWith("`"))
      return (
        <code className="inline-code" key={index}>
          {piece.slice(1, -1)}
        </code>
      );

    if (piece.startsWith("\\\*\\\*") && piece.endsWith("\\\*\\\*"))
      return <strong key={index}>{piece.slice(2, -2)}</strong>;

    return <React.Fragment key={index}>{piece}</React.Fragment>;
  });
}

function CodeBlock({ language, code }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);

      setCopied(true);

      setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="code-block">
      <div className="code-header">
        <span>{language || "code"}</span>

        <button onClick={copy}>
          {copied ? <Check size={13} /> : <Copy size={13} />}{" "}
          {copied ? "Copied" : "Copy code"}
        </button>
      </div>

      <pre>
        <code>{code}</code>
      </pre>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
