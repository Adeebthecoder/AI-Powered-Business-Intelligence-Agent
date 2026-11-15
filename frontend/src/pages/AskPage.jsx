// AskPage.jsx
// The chat-style page. The user types a question, the backend returns an
// answer (chart + insight + SQL), a clarifying question, a "blocked" notice
// or an error. All of them are shown as messages in one thread.

import { useEffect, useRef, useState } from "react";
import { useApp } from "../AppContext.jsx";
import { api } from "../api.js";
import AnswerCard from "../components/AnswerCard.jsx";
import { DatasetPicker, NoDataset } from "../components/States.jsx";

export default function AskPage() {
  const { datasetId, currentDataset, chats, addChatMessage, clearChat } = useApp();
  const [question, setQuestion] = useState("");
  const [thinking, setThinking] = useState(false);
  const [suggestions, setSuggestions] = useState({ questions: [], all_mock_questions: [] });
  const [usage, setUsage] = useState(null);
  const [showAllSuggestions, setShowAllSuggestions] = useState(false);
  const bottom = useRef(null);
  const messages = chats[datasetId] || [];

  // If the last message was a clarifying question, the next thing the user
  // types is treated as the answer to it.
  const last = messages[messages.length - 1];
  const pendingClarification =
    last && last.role === "assistant" && last.answer.status === "clarification"
      ? last.originalQuestion
      : null;

  useEffect(() => {
    if (!datasetId) return;
    api(`/api/ask/suggestions/${datasetId}`).then(setSuggestions).catch(() => {});
    api("/api/ask/usage").then(setUsage).catch(() => {});
  }, [datasetId]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, thinking]);

  async function send(text) {
    const cleaned = text.trim();
    if (!cleaned || thinking || !datasetId) return;
    setQuestion("");
    addChatMessage(datasetId, { role: "user", text: cleaned });
    setThinking(true);
    try {
      const answer = await api("/api/ask", {
        method: "POST",
        body: { dataset_id: datasetId, question: cleaned, previous_question: pendingClarification },
      });
      addChatMessage(datasetId, {
        role: "assistant",
        answer,
        // remembered so a follow-up can be linked to this question
        originalQuestion: pendingClarification || cleaned,
      });
    } catch (problem) {
      addChatMessage(datasetId, {
        role: "assistant",
        answer: { status: "error", message: problem.message },
      });
    } finally {
      setThinking(false);
      api("/api/ask/usage").then(setUsage).catch(() => {});
    }
  }

  if (!datasetId) return <div className="page"><NoDataset /></div>;

  const shownSuggestions = showAllSuggestions && suggestions.all_mock_questions.length
    ? suggestions.all_mock_questions
    : suggestions.questions;

  return (
    <div className="page ask-page">
      <header className="page-header">
        <div>
          <h1>Ask</h1>
          <p>Ask a business question in plain English about {currentDataset?.name || "your dataset"}.</p>
        </div>
        <div className="header-tools">
          {usage && usage.mode === "live" && (
            <span className="chip" title="Requests to the free AI model used today">
              AI requests today: {usage.calls_today} / {usage.daily_limit}
            </span>
          )}
          {usage && usage.mode === "mock" && (
            <span className="chip" title="Set LLM_MODE=live in the .env file to ask any question">
              Mock mode: fixed demo questions
            </span>
          )}
          <DatasetPicker />
          {messages.length > 0 && (
            <button className="btn btn-small" onClick={() => clearChat(datasetId)}>Clear chat</button>
          )}
        </div>
      </header>

      <div className="thread">
        {messages.length === 0 && (
          <div className="thread-empty">
            <h2>What would you like to know?</h2>
            <p className="muted">
              Each answer comes with a chart, a short explanation and the SQL that produced it.
            </p>
          </div>
        )}

        {messages.map((message, index) =>
          message.role === "user" ? (
            <div className="bubble-row user" key={index}>
              <div className="bubble">{message.text}</div>
            </div>
          ) : (
            <div className="bubble-row" key={index}>
              <AnswerCard answer={message.answer} />
            </div>
          )
        )}

        {thinking && (
          <div className="bubble-row">
            <div className="answer thinking">
              <div className="spinner small" />
              Writing SQL, checking it, running it and preparing the answer...
            </div>
          </div>
        )}
        <div ref={bottom} />
      </div>

      <div className="composer-area">
        {shownSuggestions.length > 0 && !thinking && (
          <div className="suggestions">
            {shownSuggestions.map((item) => (
              <button key={item} className="suggestion" onClick={() => send(item)}>{item}</button>
            ))}
            {suggestions.all_mock_questions.length > suggestions.questions.length && (
              <button className="link-button" onClick={() => setShowAllSuggestions(!showAllSuggestions)}>
                {showAllSuggestions ? "Show fewer" : "Show all demo questions"}
              </button>
            )}
          </div>
        )}
        <form className="composer" onSubmit={(event) => { event.preventDefault(); send(question); }}>
          <input
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder={pendingClarification
              ? "Type your answer to the question above..."
              : "For example: Which region had the highest revenue last quarter?"}
            maxLength={500}
            disabled={thinking}
            aria-label="Your question"
          />
          <button className="btn btn-primary" disabled={thinking || !question.trim()}>Ask</button>
        </form>
      </div>
    </div>
  );
}
