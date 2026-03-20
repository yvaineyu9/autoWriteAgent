import { useEffect, useState } from "react";
import { api, subscribeTask } from "./api";

const EMPTY_FORM = {
  title: "",
  body: "",
  persona: "chongxiaoyu",
  platform: "xiaohongshu",
  tags: "",
};

export function App() {
  const [inspirations, setInspirations] = useState([]);
  const [publications, setPublications] = useState([]);
  const [form, setForm] = useState(EMPTY_FORM);
  const [selectionGoal, setSelectionGoal] = useState("本周发 3 篇小红书内容，优先高信息价值的稿件");
  const [taskLog, setTaskLog] = useState([]);

  async function refresh() {
    const [nextInspirations, nextPublications] = await Promise.all([
      api.listInspirations(),
      api.listPublications(),
    ]);
    setInspirations(nextInspirations);
    setPublications(nextPublications);
  }

  useEffect(() => {
    refresh().catch((error) => {
      setTaskLog((current) => [...current, `加载失败: ${error.message}`]);
    });
  }, []);

  async function handleCreate(event) {
    event.preventDefault();
    const created = await api.createInspiration({
      title: form.title,
      body: form.body,
      persona: form.persona,
      platform: form.platform,
      tags: form.tags.split(",").map((item) => item.trim()).filter(Boolean),
    });
    setForm(EMPTY_FORM);
    setInspirations((current) => [created, ...current]);
  }

  async function handleDraft(item) {
    if (!item.content_id) return;
    const task = await api.createDraft(item.content_id, {
      persona: item.persona || "chongxiaoyu",
      platform: item.platform || "xiaohongshu",
      input_path: item.path,
    });
    setTaskLog((current) => [...current, `任务已创建: ${task.task_id}`]);
    const close = subscribeTask(task.task_id, (message) => {
      setTaskLog((current) => [...current, `${message.event}: ${JSON.stringify(message.payload)}`]);
      if (message.event === "task.succeeded" || message.event === "task.failed") {
        close();
        refresh().catch(() => {});
      }
    });
  }

  async function handleFinalize(item) {
    if (!item.content_id) return;
    await api.finalizeContent(item.content_id);
    refresh();
  }

  async function handleSelection() {
    const task = await api.recommendSelection({ goal: selectionGoal, limit: 10 });
    setTaskLog((current) => [...current, `选稿任务已创建: ${task.task_id}`]);
    const close = subscribeTask(task.task_id, (message) => {
      setTaskLog((current) => [...current, `${message.event}: ${JSON.stringify(message.payload)}`]);
      if (message.event === "task.succeeded" || message.event === "task.failed") {
        close();
      }
    });
  }

  return (
    <div className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">Claude Workflows</p>
          <h1>内容工厂 Web UI</h1>
          <p className="subcopy">先把灵感池、写作任务、选稿入口和发布看板打通。</p>
        </div>
      </header>

      <main className="grid">
        <section className="panel">
          <h2>灵感池</h2>
          <form className="stack" onSubmit={handleCreate}>
            <input
              placeholder="标题"
              value={form.title}
              onChange={(event) => setForm({ ...form, title: event.target.value })}
            />
            <textarea
              rows={6}
              placeholder="写下灵感"
              value={form.body}
              onChange={(event) => setForm({ ...form, body: event.target.value })}
            />
            <div className="inline">
              <input
                placeholder="persona"
                value={form.persona}
                onChange={(event) => setForm({ ...form, persona: event.target.value })}
              />
              <input
                placeholder="platform"
                value={form.platform}
                onChange={(event) => setForm({ ...form, platform: event.target.value })}
              />
            </div>
            <input
              placeholder="tags，逗号分隔"
              value={form.tags}
              onChange={(event) => setForm({ ...form, tags: event.target.value })}
            />
            <button type="submit">录入灵感</button>
          </form>
          <div className="card-list">
            {inspirations.map((item) => (
              <article className="card" key={item.path}>
                <div className="card-meta">
                  <span>{item.status}</span>
                  <span>{item.persona || "未指定 persona"}</span>
                </div>
                <h3>{item.title}</h3>
                <p>{item.summary}</p>
                <div className="inline">
                  <button onClick={() => handleDraft(item)}>发起写作</button>
                  <button className="ghost" onClick={() => handleFinalize(item)}>
                    标记定稿
                  </button>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="panel">
          <h2>选稿台</h2>
          <textarea rows={5} value={selectionGoal} onChange={(event) => setSelectionGoal(event.target.value)} />
          <button onClick={handleSelection}>生成推荐</button>

          <h2>发布台</h2>
          <div className="card-list compact">
            {publications.map((item) => (
              <article className="card" key={item.id}>
                <div className="card-meta">
                  <span>{item.status}</span>
                  <span>{item.persona_name}</span>
                </div>
                <h3>{item.title}</h3>
                <p>{item.platform}:{item.account_name}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="panel">
          <h2>任务流</h2>
          <div className="log">
            {taskLog.map((line, index) => (
              <pre key={`${line}-${index}`}>{line}</pre>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
