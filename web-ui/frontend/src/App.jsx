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
  const [draftContents, setDraftContents] = useState([]);
  const [finalContents, setFinalContents] = useState([]);
  const [publications, setPublications] = useState([]);
  const [selectedContent, setSelectedContent] = useState(null);
  const [editableBody, setEditableBody] = useState("");
  const [editableTitle, setEditableTitle] = useState("");
  const [form, setForm] = useState(EMPTY_FORM);
  const [selectionGoal, setSelectionGoal] = useState("本周发 3 篇小红书内容，优先高信息价值的稿件");
  const [taskLog, setTaskLog] = useState([]);
  const [busyContentIds, setBusyContentIds] = useState([]);
  const [selectedForPublishing, setSelectedForPublishing] = useState([]);
  const [personaOverrides, setPersonaOverrides] = useState({});
  const [selectionRecommendations, setSelectionRecommendations] = useState([]);
  const [publicationForms, setPublicationForms] = useState({});

  async function refresh() {
    const [nextInspirations, nextDrafts, nextFinals, nextPublications] = await Promise.all([
      api.listInspirations(),
      api.listContents("draft"),
      api.listContents("final"),
      api.listPublications(),
    ]);
    setInspirations(nextInspirations);
    setDraftContents(nextDrafts);
    setFinalContents(nextFinals);
    setPublications(nextPublications);
  }

  async function showContent(contentId) {
    const content = await api.getContent(contentId);
    setSelectedContent(content);
    setEditableTitle(content.title || "");
    setEditableBody(content.body || "");
  }

  async function handlePersonaChange(item, persona) {
    setPersonaOverrides((current) => ({ ...current, [item.path]: persona }));
    try {
      await api.updateInspiration(item.path, { persona });
      refresh();
    } catch (error) {
      setTaskLog((current) => [...current, `更新账号失败: ${error.message}`]);
    }
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
    try {
      const activeItem = item.content_id ? item : await api.activateInspiration(item.path);
      setBusyContentIds((current) => [...new Set([...current, activeItem.content_id])]);
      const persona = personaOverrides[item.path] || activeItem.persona || "chongxiaoyu";
      const task = await api.createDraft(activeItem.content_id, {
        persona,
        platform: activeItem.platform || "xiaohongshu",
        input_path: item.path,
      });
      setTaskLog((current) => [...current, `任务已创建: ${task.task_id}`]);
      const close = subscribeTask(task.task_id, (message) => {
        setTaskLog((current) => [...current, `${message.event}: ${JSON.stringify(message.payload)}`]);
        if (message.event === "task.succeeded" || message.event === "task.failed") {
          if (message.event === "task.succeeded") {
            setTaskLog((current) => [...current, "写作任务完成，刷新后可查看最新状态。"]);
          }
          setBusyContentIds((current) => current.filter((id) => id !== activeItem.content_id));
          close();
          refresh().catch(() => {});
        }
      });
    } catch (error) {
      if (item.content_id) {
        setBusyContentIds((current) => current.filter((id) => id !== item.content_id));
      }
      setTaskLog((current) => [...current, `发起写作失败: ${error.message}`]);
    }
  }

  async function handleFinalize(item) {
    try {
      const activeItem = item.content_id ? item : await api.activateInspiration(item.path);
      await api.finalizeContent(activeItem.content_id);
      setTaskLog((current) => [...current, `已定稿: ${activeItem.title}`]);
      refresh();
    } catch (error) {
      setTaskLog((current) => [...current, `标记定稿失败: ${error.message}`]);
    }
  }

  async function handleSelection() {
    const result = await api.recommendSelection({ goal: selectionGoal, limit: 10 });
    if (!result.task_id) {
      const count = result.recommendations?.length || 0;
      setSelectionRecommendations(result.recommendations || []);
      setTaskLog((current) => [...current, `当前没有可选稿件，推荐结果数: ${count}`]);
      return;
    }
    setTaskLog((current) => [...current, `选稿任务已创建: ${result.task_id}`]);
    const close = subscribeTask(result.task_id, (message) => {
      setTaskLog((current) => [...current, `${message.event}: ${JSON.stringify(message.payload)}`]);
      if (message.event === "task.completed") {
        setSelectionRecommendations(message.payload.recommendations || []);
      }
      if (message.event === "task.succeeded" || message.event === "task.failed") {
        close();
      }
    });
  }

  async function handleSelectionConfirm() {
    if (!selectedForPublishing.length) {
      setTaskLog((current) => [...current, "请先勾选要发布的定稿内容。"]);
      return;
    }
    const result = await api.confirmSelection({ content_ids: selectedForPublishing });
    setTaskLog((current) => [...current, `已创建发布记录: ${result.publication_ids.join(", ") || "无"}`]);
    setSelectedForPublishing([]);
    refresh();
  }

  async function handlePublish(publicationId) {
    const form = publicationForms[publicationId] || {};
    await api.publishPublication(publicationId, { post_url: form.post_url || "" });
    setTaskLog((current) => [...current, `已标记发布记录 #${publicationId} 为 published`]);
    refresh();
  }

  async function handleMetricSave(publicationId) {
    const form = publicationForms[publicationId] || {};
    await api.createPublicationMetric(publicationId, {
      views: Number(form.views || 0),
      likes: Number(form.likes || 0),
      collects: Number(form.collects || 0),
      comments: Number(form.comments || 0),
      shares: Number(form.shares || 0),
      notes: form.notes || "",
    });
    setTaskLog((current) => [...current, `已录入发布记录 #${publicationId} 的数据快照`]);
    refresh();
  }

  function updatePublicationForm(publicationId, key, value) {
    setPublicationForms((current) => ({
      ...current,
      [publicationId]: {
        ...(current[publicationId] || {}),
        [key]: value,
      },
    }));
  }

  async function handleSaveContent() {
    if (!selectedContent) return;
    const saved = await api.saveContent(selectedContent.content_id, {
      title: editableTitle,
      body: editableBody,
    });
    setSelectedContent(saved);
    setEditableTitle(saved.title || "");
    setEditableBody(saved.body || "");
    setTaskLog((current) => [...current, `已保存内容: ${saved.title}`]);
    refresh();
  }

  return (
    <div className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">Claude Workflows</p>
          <h1>内容工厂 Web UI</h1>
          <p className="subcopy">先录入灵感，再点卡片里的“发起写作”。任务完成后刷新页面看状态变化。</p>
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
                  <span>{personaOverrides[item.path] || item.persona || "未指定账号"}</span>
                </div>
                <h3>{item.title}</h3>
                <p className="summary">{item.summary}</p>
                <div className="inline">
                  <select
                    value={personaOverrides[item.path] || item.persona || "chongxiaoyu"}
                    onChange={(event) => handlePersonaChange(item, event.target.value)}
                  >
                    <option value="chongxiaoyu">虫小宇</option>
                    <option value="yuejian">月见</option>
                  </select>
                  <button className="ghost" onClick={() => item.content_id && showContent(item.content_id)}>
                    看详情
                  </button>
                </div>
                <div className="inline">
                  <button
                    onClick={() => handleDraft(item)}
                    disabled={item.content_id && busyContentIds.includes(item.content_id)}
                  >
                    {item.content_id && busyContentIds.includes(item.content_id) ? "写作中..." : "发起写作"}
                  </button>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="panel">
          <h2>选稿台</h2>
          <textarea rows={5} value={selectionGoal} onChange={(event) => setSelectionGoal(event.target.value)} />
          <div className="inline">
            <button onClick={handleSelection}>生成推荐</button>
            <button className="ghost" onClick={handleSelectionConfirm}>确认选稿</button>
          </div>
          <div className="card-list compact">
            {selectionRecommendations.map((item) => (
              <article className="card" key={item.content_id || item.title}>
                <h3>{item.title || item.content_id}</h3>
                <p>{item.reason || "无推荐理由"}</p>
              </article>
            ))}
          </div>
          <div className="card-list compact">
            {finalContents.map((item) => (
              <label className="card" key={item.content_id}>
                <div className="card-meta">
                  <span>{item.status}</span>
                  <span>{item.persona_id || "未指定"}</span>
                </div>
                <h3>{item.title}</h3>
                <p>{item.platform || "未指定平台"}</p>
                <div className="inline">
                  <input
                    type="checkbox"
                    checked={selectedForPublishing.includes(item.content_id)}
                    onChange={(event) => {
                      setSelectedForPublishing((current) =>
                        event.target.checked
                          ? [...current, item.content_id]
                          : current.filter((id) => id !== item.content_id)
                      );
                    }}
                  />
                  <button type="button" className="ghost" onClick={() => showContent(item.content_id)}>预览</button>
                </div>
              </label>
            ))}
          </div>

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
                <input
                  placeholder="发布链接"
                  value={(publicationForms[item.id] || {}).post_url || ""}
                  onChange={(event) => updatePublicationForm(item.id, "post_url", event.target.value)}
                />
                <div className="inline">
                  <button onClick={() => handlePublish(item.id)}>标记已发布</button>
                </div>
                <div className="inline metrics">
                  <input
                    placeholder="阅读"
                    value={(publicationForms[item.id] || {}).views || ""}
                    onChange={(event) => updatePublicationForm(item.id, "views", event.target.value)}
                  />
                  <input
                    placeholder="点赞"
                    value={(publicationForms[item.id] || {}).likes || ""}
                    onChange={(event) => updatePublicationForm(item.id, "likes", event.target.value)}
                  />
                  <input
                    placeholder="收藏"
                    value={(publicationForms[item.id] || {}).collects || ""}
                    onChange={(event) => updatePublicationForm(item.id, "collects", event.target.value)}
                  />
                  <input
                    placeholder="评论"
                    value={(publicationForms[item.id] || {}).comments || ""}
                    onChange={(event) => updatePublicationForm(item.id, "comments", event.target.value)}
                  />
                  <input
                    placeholder="分享"
                    value={(publicationForms[item.id] || {}).shares || ""}
                    onChange={(event) => updatePublicationForm(item.id, "shares", event.target.value)}
                  />
                </div>
                <div className="inline">
                  <button className="ghost" onClick={() => handleMetricSave(item.id)}>录入数据</button>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="panel">
          <h2>编辑台</h2>
          <div className="card-list compact">
            {draftContents.map((item) => (
              <article className="card" key={item.content_id}>
                <div className="card-meta">
                  <span>{item.status}</span>
                  <span>{item.persona_id || "未指定"}</span>
                </div>
                <h3>{item.title}</h3>
                <p>{item.platform || "未指定平台"}</p>
                <div className="inline">
                  <button className="ghost" onClick={() => showContent(item.content_id)}>查看内容</button>
                  <button onClick={() => handleFinalize(item)}>标记定稿</button>
                </div>
              </article>
            ))}
          </div>

          <h2>内容详情</h2>
          <div className="preview">
            {selectedContent ? (
              <>
                <div className="inline">
                  <button className="ghost" onClick={() => setSelectedContent(null)}>返回列表</button>
                  <button onClick={handleSaveContent}>保存修改</button>
                </div>
                <p className="eyebrow">{selectedContent.status}</p>
                <input value={editableTitle} onChange={(event) => setEditableTitle(event.target.value)} />
                <p>{selectedContent.resolved_path || "暂无文件路径"}</p>
                <textarea rows={18} value={editableBody} onChange={(event) => setEditableBody(event.target.value)} />
              </>
            ) : (
              <p>点“查看内容”或“预览”后，这里会显示正文。</p>
            )}
          </div>

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
