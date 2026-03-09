async function readSSE(response, onEvent) {
  if (!response.ok) throw new Error('HTTP ' + response.status);
  if (!response.body) throw new Error('当前浏览器不支持流式响应');

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split('\\n\\n');
    buffer = events.pop() || '';

    for (const event of events) {
      const line = event.split('\\n').find((item) => item.startsWith('data: '));
      if (!line) continue;
      onEvent(JSON.parse(line.slice(6)));
    }
  }

  buffer += decoder.decode();
  if (buffer.trim()) {
    const line = buffer.split('\\n').find((item) => item.startsWith('data: '));
    if (line) onEvent(JSON.parse(line.slice(6)));
  }
}

function formatValue(value) {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value;
  return JSON.stringify(value, null, 2);
}

function createProgressPanel(chapter) {
  const panel = document.createElement('div');
  panel.id = 'progressPanel';
  panel.style.cssText = 'position:fixed;top:20px;right:20px;width:430px;max-height:85vh;overflow:hidden;background:white;border:2px solid #28a745;border-radius:10px;box-shadow:0 12px 32px rgba(0,0,0,0.22);z-index:99999;padding:18px;';
  panel.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px;">
      <div>
        <div style="font-size:18px;font-weight:700;color:#1f6f43;">第 ${chapter} 章状态更新</div>
        <div id="progressStatus" style="font-size:13px;color:#4b6356;margin-top:4px;">准备中...</div>
      </div>
      <button id="progressClose" type="button" class="btn btn-sm btn-outline-secondary">关闭</button>
    </div>
    <div id="progressCharacters" style="max-height:300px;overflow-y:auto;border:1px solid #d7e8db;border-radius:8px;padding:10px;background:#f8fcf9;"></div>
    <div style="margin-top:12px;">
      <div style="font-size:13px;font-weight:700;color:#345244;margin-bottom:6px;">实时日志</div>
      <div id="progressLog" style="max-height:180px;overflow-y:auto;border:1px solid #e5e7eb;border-radius:8px;padding:8px;background:#fafafa;font-size:12px;line-height:1.5;"></div>
    </div>
    <div id="progressActions" style="display:none;gap:8px;margin-top:12px;">
      <button id="progressRefresh" type="button" class="btn btn-sm btn-success">刷新页面</button>
    </div>
  `;
  document.body.appendChild(panel);
  document.getElementById('progressClose').onclick = () => {
    if (document.body.contains(panel)) document.body.removeChild(panel);
  };
  return panel;
}

function appendProgressLog(text, tone = 'normal') {
  const log = document.getElementById('progressLog');
  if (!log) return;
  const row = document.createElement('div');
  const color = tone === 'error' ? '#b42318' : tone === 'success' ? '#067647' : '#344054';
  row.style.cssText = `padding:4px 2px;border-bottom:1px dashed #e5e7eb;color:${color};white-space:pre-wrap;`;
  row.textContent = text;
  log.appendChild(row);
  log.scrollTop = log.scrollHeight;
}

function ensureCharacterCard(character) {
  const container = document.getElementById('progressCharacters');
  if (!container) return null;

  let card = container.querySelector(`[data-character="${character}"]`);
  if (card) return card;

  card = document.createElement('div');
  card.dataset.character = character;
  card.style.cssText = 'border:1px solid #cfe3d4;border-radius:8px;background:white;padding:10px;margin-bottom:10px;';

  const title = document.createElement('div');
  title.className = 'character-title';
  title.style.cssText = 'font-weight:700;color:#1f2937;margin-bottom:8px;';
  title.textContent = character || '未命名角色';

  const reason = document.createElement('div');
  reason.className = 'character-reason';
  reason.style.cssText = 'font-size:12px;color:#6b7280;margin-bottom:8px;';

  const fields = document.createElement('div');
  fields.className = 'character-fields';
  fields.style.cssText = 'display:flex;flex-direction:column;gap:6px;';

  card.appendChild(title);
  card.appendChild(reason);
  card.appendChild(fields);
  container.appendChild(card);
  return card;
}

function renderFieldUpdate(payload) {
  const card = ensureCharacterCard(payload.character || '未命名角色');
  if (!card) return;

  const reason = card.querySelector('.character-reason');
  const chapterText = payload.chapter ? `第 ${payload.chapter} 章` : '';
  const reasonText = payload.reason ? `原因：${payload.reason}` : '';
  reason.textContent = [chapterText, reasonText].filter(Boolean).join(' | ');

  const fields = card.querySelector('.character-fields');
  const row = document.createElement('div');
  row.style.cssText = 'padding:6px 8px;border-radius:6px;background:#f3faf5;border:1px solid #d8efe0;';

  const name = document.createElement('div');
  name.style.cssText = 'font-size:12px;color:#067647;font-weight:700;';
  name.textContent = `${payload.action || '更新'} ${payload.field}`;

  const value = document.createElement('pre');
  value.style.cssText = 'margin:4px 0 0 0;white-space:pre-wrap;font-size:12px;color:#111827;background:transparent;border:0;';
  value.textContent = formatValue(payload.value);

  row.appendChild(name);
  row.appendChild(value);
  fields.appendChild(row);
}

document.getElementById('generateForm').onsubmit = async (e) => {
  e.preventDefault();

  const form = e.target;
  const data = {
    chapter: parseInt(form.chapter.value, 10),
    summary: form.summary.value
  };

  document.getElementById('streamOutput').style.display = 'block';
  form.style.display = 'none';

  const statusMsg = document.getElementById('statusMsg');
  const contentStream = document.getElementById('contentStream');
  contentStream.textContent = '';

  try {
    const response = await fetch('/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });

    await readSSE(response, (payload) => {
      if (payload.type === 'status') statusMsg.textContent = payload.message;
      else if (payload.type === 'content') contentStream.textContent += payload.text;
      else if (payload.type === 'done') {
        alert('生成完成');
        location.reload();
      } else if (payload.type === 'error') {
        alert('错误: ' + payload.message);
        location.reload();
      }
    });
  } catch (err) {
    alert('错误: ' + err.message);
    form.style.display = 'block';
  }
};

async function regenerate(ch) {
  if (!confirm('确定根据第 ' + ch + ' 章内容更新角色状态？')) return;

  const existing = document.getElementById('progressPanel');
  if (existing && document.body.contains(existing)) existing.remove();

  const panel = createProgressPanel(ch);
  appendProgressLog('已发起状态更新请求。');

  try {
    const response = await fetch('/regenerate_states/' + ch, { method: 'POST' });

    await readSSE(response, (payload) => {
      const statusNode = document.getElementById('progressStatus');

      if (payload.type === 'status' && statusNode) {
        statusNode.textContent = payload.message;
        appendProgressLog(payload.message);
      } else if (payload.type === 'agent_note') {
        appendProgressLog('Agent: ' + payload.message);
      } else if (payload.type === 'tool_call') {
        const fields = (payload.field_names || []).join('、');
        const summary = `${payload.action || '处理'}角色 ${payload.character || '未命名角色'}${fields ? '，字段：' + fields : ''}`;
        appendProgressLog(summary);
      } else if (payload.type === 'field_update') {
        renderFieldUpdate(payload);
        appendProgressLog(`已写入 ${payload.character} -> ${payload.field}`);
      } else if (payload.type === 'tool_result') {
        appendProgressLog(`角色 ${payload.character || '未命名角色'} 已写入完成`, 'success');
      } else if (payload.type === 'tool_error') {
        appendProgressLog(`角色 ${payload.character || '未命名角色'} 更新失败：${payload.message}`, 'error');
      } else if (payload.type === 'done') {
        if (statusNode) statusNode.textContent = '状态更新完成。你可以先检查上面的写入记录，再决定是否刷新页面。';
        appendProgressLog('状态更新完成。', 'success');
        const actions = document.getElementById('progressActions');
        const refresh = document.getElementById('progressRefresh');
        if (actions) actions.style.display = 'flex';
        if (refresh) refresh.onclick = () => location.reload();
      } else if (payload.type === 'error') {
        if (statusNode) statusNode.textContent = '状态更新失败。';
        appendProgressLog('错误: ' + payload.message, 'error');
        const actions = document.getElementById('progressActions');
        const refresh = document.getElementById('progressRefresh');
        if (actions) actions.style.display = 'flex';
        if (refresh) refresh.textContent = '重新加载页面';
        alert('错误: ' + payload.message);
      }
    });
  } catch (err) {
    const statusNode = document.getElementById('progressStatus');
    if (statusNode) statusNode.textContent = '请求失败。';
    appendProgressLog('请求失败: ' + err.message, 'error');
    alert('请求失败: ' + err.message);
  }
}
