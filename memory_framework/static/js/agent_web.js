window.AgentWeb = (() => {
    let generationStreamController = null;
    let activeGenerationTaskId = null;

    function applyRipple(event) {
        const target = event.currentTarget;
        const rect = target.getBoundingClientRect();
        const ripple = document.createElement("span");
        const size = Math.max(rect.width, rect.height);
        ripple.className = "material-ripple";
        ripple.style.width = `${size}px`;
        ripple.style.height = `${size}px`;
        ripple.style.left = `${event.clientX - rect.left - size / 2}px`;
        ripple.style.top = `${event.clientY - rect.top - size / 2}px`;
        target.appendChild(ripple);
        ripple.addEventListener("animationend", () => ripple.remove(), { once: true });
    }

    function initRipples() {
        document.querySelectorAll(".btn, .quick-link, .stack-item, .site-nav a, .fab").forEach((element) => {
            if (element.dataset.rippleBound === "true") {
                return;
            }
            element.dataset.rippleBound = "true";
            element.addEventListener("pointerdown", applyRipple);
        });
    }

    async function parseResponse(response) {
        let data = {};
        try {
            data = await response.json();
        } catch (error) {
            data = {};
        }
        return { ok: response.ok, data };
    }

    async function postJSON(url, payload) {
        const response = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        return parseResponse(response);
    }

    async function deleteJSON(url) {
        const response = await fetch(url, { method: "DELETE" });
        return parseResponse(response);
    }

    async function deleteJSONAndReload(url) {
        if (!confirm("确定执行删除操作？")) {
            return;
        }
        const result = await deleteJSON(url);
        if (!result.ok) {
            alert(result.data.error || "操作失败");
            return;
        }
        location.reload();
    }

    async function deleteProject(projectId) {
        if (!confirm("确定删除这个项目？")) {
            return;
        }
        const result = await deleteJSON(`/projects/${projectId}`);
        if (!result.ok) {
            alert(result.data.error || "删除失败");
            return;
        }
        location.reload();
    }

    async function deleteCharacter(projectId, name) {
        if (!confirm(`确定删除角色 ${name}？`)) {
            return;
        }
        const result = await deleteJSON(`/project/${projectId}/character/${encodeURIComponent(name)}`);
        if (!result.ok) {
            alert(result.data.error || "删除失败");
            return;
        }
        location.reload();
    }

    function addFieldRow(containerId) {
        const container = document.getElementById(containerId);
        if (!container) {
            return;
        }
        const row = document.createElement("div");
        row.className = "form-grid full-span";
        row.innerHTML = `
            <label><span>字段名</span><input class="form-control" data-field-key></label>
            <label><span>字段值</span><input class="form-control" data-field-value></label>
        `;
        container.appendChild(row);
        initRipples();
    }

    function collectFieldRows(containerId) {
        const container = document.getElementById(containerId);
        const fields = {};
        if (!container) {
            return fields;
        }
        container.querySelectorAll("[data-field-key]").forEach((node) => {
            const key = node.value.trim();
            const valueNode = node.closest("div").querySelector("[data-field-value]");
            if (key && valueNode) {
                fields[key] = valueNode.value;
            }
        });
        return fields;
    }

    function renderSimpleMarkdown(text) {
        return text
            .replace(/^### (.*)$/gm, "<h3>$1</h3>")
            .replace(/^## (.*)$/gm, "<h2>$1</h2>")
            .replace(/^# (.*)$/gm, "<h1>$1</h1>")
            .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
            .replace(/\n/g, "<br>");
    }

    function setupOutlinePreview(inputId, previewId) {
        const input = document.getElementById(inputId);
        const preview = document.getElementById(previewId);
        if (!input || !preview) {
            return;
        }
        const render = () => {
            preview.innerHTML = input.value.trim()
                ? renderSimpleMarkdown(input.value)
                : "这里会实时预览大纲内容。";
        };
        input.addEventListener("input", render);
        render();
    }

    async function readSSE(response, onEvent) {
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        if (!response.body) {
            throw new Error("当前浏览器不支持流式响应");
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) {
                break;
            }

            buffer += decoder.decode(value, { stream: true });
            const chunks = buffer.split("\n\n");
            buffer = chunks.pop() || "";

            for (const chunk of chunks) {
                const line = chunk.split("\n").find((item) => item.startsWith("data: "));
                if (!line) {
                    continue;
                }
                onEvent(JSON.parse(line.slice(6)));
            }
        }
    }

    function appendLog(container, text, tone = "normal") {
        if (!container) {
            return;
        }
        const row = document.createElement("div");
        row.className = "stream-log-row";
        row.style.color = tone === "error" ? "#d93025" : tone === "success" ? "#1e8e3e" : "#455468";
        row.textContent = text;
        container.appendChild(row);
        container.scrollTop = container.scrollHeight;
    }

    function formatValue(value) {
        if (value === null || value === undefined) {
            return "";
        }
        return typeof value === "string" ? value : JSON.stringify(value, null, 2);
    }

    function renderPromptCapture(data) {
        const panel = document.getElementById("promptPanel");
        const finalPromptView = document.getElementById("finalPromptView");
        const messagePromptView = document.getElementById("messagePromptView");
        const promptPath = document.getElementById("promptPath");

        if (!panel || !finalPromptView || !messagePromptView) {
            return;
        }

        panel.hidden = false;
        finalPromptView.textContent = data.final_prompt || "";
        messagePromptView.textContent = JSON.stringify(data.messages || [], null, 2);
        if (promptPath) {
            promptPath.textContent = data.path ? `已保存: ${data.path}` : "";
        }
    }

    function renderStatePromptCapture(data) {
        const panel = document.getElementById("promptPanel");
        const statePromptView = document.getElementById("statePromptView");
        const stateMessagePromptView = document.getElementById("stateMessagePromptView");
        const statePromptPath = document.getElementById("statePromptPath");

        if (!panel || !statePromptView || !stateMessagePromptView) {
            return;
        }

        panel.hidden = false;
        statePromptView.textContent = data.final_prompt || "";
        stateMessagePromptView.textContent = JSON.stringify(data.messages || [], null, 2);
        if (statePromptPath) {
            statePromptPath.textContent = data.path ? `已保存: ${data.path}` : "";
        }
    }

    function openProgressDrawer(title) {
        const existing = document.getElementById("floatingProgress");
        if (existing) {
            existing.remove();
        }

        const drawer = document.createElement("section");
        drawer.id = "floatingProgress";
        drawer.className = "floating-progress";
        drawer.innerHTML = `
            <div class="progress-head">
                <div>
                    <div class="eyebrow">State Update</div>
                    <h3>${title}</h3>
                    <div id="progressStatus" class="item-subtle">准备中...</div>
                </div>
                <button class="btn btn-sm btn-outline-secondary" id="closeProgressBtn" type="button">关闭</button>
            </div>
            <div class="progress-body">
                <div class="progress-section">
                    <div class="eyebrow">角色写入</div>
                    <div id="progressCharacters" class="progress-characters"></div>
                </div>
                <div class="progress-section">
                    <div class="eyebrow">实时日志</div>
                    <div id="progressLog" class="progress-log"></div>
                </div>
            </div>
        `;
        document.body.appendChild(drawer);
        document.getElementById("closeProgressBtn").onclick = () => drawer.remove();
        initRipples();
        return drawer;
    }

    function ensureCharacterCard(character) {
        const container = document.getElementById("progressCharacters");
        if (!container) {
            return null;
        }

        let card = container.querySelector(`[data-character="${character}"]`);
        if (card) {
            return card;
        }

        card = document.createElement("div");
        card.className = "progress-character";
        card.dataset.character = character;
        card.innerHTML = `<strong>${character || "未命名角色"}</strong><div class="progress-fields"></div>`;
        container.appendChild(card);
        return card;
    }

    function renderFieldUpdate(payload) {
        const card = ensureCharacterCard(payload.character || "未命名角色");
        if (!card) {
            return;
        }
        const fields = card.querySelector(".progress-fields");
        const row = document.createElement("div");
        row.className = "progress-field";
        row.innerHTML = `<div><strong>${payload.field}</strong></div><div>${formatValue(payload.value)}</div>`;
        fields.appendChild(row);
    }

    function getGenerationNodes() {
        return {
            streamPanel: document.getElementById("streamPanel"),
            statusMsg: document.getElementById("statusMsg"),
            contentStream: document.getElementById("contentStream"),
            generateLog: document.getElementById("generateLog"),
            promptPanel: document.getElementById("promptPanel"),
            statePromptView: document.getElementById("statePromptView"),
            stateMessagePromptView: document.getElementById("stateMessagePromptView"),
            statePromptPath: document.getElementById("statePromptPath"),
        };
    }

    function prepareGenerationView({ reset = false, scroll = false } = {}) {
        const nodes = getGenerationNodes();
        if (nodes.streamPanel) {
            nodes.streamPanel.hidden = false;
            if (scroll) {
                nodes.streamPanel.scrollIntoView({ behavior: "smooth", block: "start" });
            }
        }
        if (reset) {
            if (nodes.contentStream) {
                nodes.contentStream.textContent = "";
            }
            if (nodes.generateLog) {
                nodes.generateLog.innerHTML = "";
            }
            if (nodes.promptPanel) {
                nodes.promptPanel.hidden = true;
            }
            if (nodes.statePromptView) {
                nodes.statePromptView.textContent = "";
            }
            if (nodes.stateMessagePromptView) {
                nodes.stateMessagePromptView.textContent = "";
            }
            if (nodes.statePromptPath) {
                nodes.statePromptPath.textContent = "";
            }
        }
        return nodes;
    }

    function handleGenerationEvent(projectId, data, nodes, options = {}) {
        const { autoRedirect = true } = options;
        if (data.type === "status") {
            if (nodes.statusMsg) {
                nodes.statusMsg.textContent = data.message;
            }
            appendLog(nodes.generateLog, data.message);
        } else if (data.type === "prompt_capture") {
            renderPromptCapture(data);
            appendLog(nodes.generateLog, "已捕获本次调用前的最终 Prompt。", "success");
        } else if (data.type === "state_prompt_capture") {
            renderStatePromptCapture(data);
            appendLog(nodes.generateLog, "已捕获状态更新前的 Prompt。", "success");
        } else if (data.type === "content") {
            if (nodes.contentStream) {
                nodes.contentStream.textContent += data.text;
            }
        } else if (data.type === "field_update") {
            appendLog(nodes.generateLog, `[写入] ${data.character} -> ${data.field}: ${formatValue(data.value)}`);
        } else if (data.type === "tool_call") {
            appendLog(nodes.generateLog, `[工具] ${data.tool_name || "tool"} ${data.character || ""}`);
        } else if (data.type === "tool_result" || data.type === "query_summary" || data.type === "post_process") {
            appendLog(nodes.generateLog, data.message || JSON.stringify(data), data.status === "error" ? "error" : "normal");
        } else if (data.type === "agent_note") {
            appendLog(nodes.generateLog, `[Agent] ${data.message}`);
        } else if (data.type === "tool_error" || data.type === "error") {
            appendLog(nodes.generateLog, data.message || "发生错误", "error");
            alert(data.message || "生成失败");
        } else if (data.type === "done") {
            appendLog(nodes.generateLog, "章节生成完成。", "success");
            activeGenerationTaskId = null;
            if (autoRedirect) {
                location.href = data.redirect || `/project/${projectId}/chapter/${data.chapter}`;
            }
        }
    }

    async function connectGenerationTask(projectId, taskId, options = {}) {
        const { reset = false, scroll = false, autoRedirect = true } = options;
        if (activeGenerationTaskId === taskId) {
            return;
        }
        if (generationStreamController) {
            generationStreamController.abort();
        }

        activeGenerationTaskId = taskId;
        generationStreamController = new AbortController();
        const nodes = prepareGenerationView({ reset, scroll });
        appendLog(nodes.generateLog, `已连接后台任务 ${taskId}，离开页面不会中断。`, "success");

        try {
            const response = await fetch(`/project/${projectId}/generate/tasks/${taskId}/stream`, {
                signal: generationStreamController.signal,
            });
            await readSSE(response, (data) => handleGenerationEvent(projectId, data, nodes, { autoRedirect }));
        } catch (error) {
            if (error.name === "AbortError") {
                return;
            }
            appendLog(nodes.generateLog, error.message, "error");
            alert(error.message);
        } finally {
            if (activeGenerationTaskId === taskId) {
                activeGenerationTaskId = null;
            }
        }
    }

    async function resumeLatestGenerationTask(projectId) {
        const result = await parseResponse(await fetch(`/project/${projectId}/generate/tasks/latest`));
        if (!result.ok || !result.data.active || !result.data.task) {
            return;
        }
        connectGenerationTask(projectId, result.data.task.id, { reset: true, scroll: false, autoRedirect: true });
    }

    function setupChapterGeneration(projectId) {
        const form = document.getElementById("generateForm");
        if (!form) {
            return;
        }

        const submitButton = form.querySelector('button[type="submit"]');
        resumeLatestGenerationTask(projectId);

        form.addEventListener("submit", async (event) => {
            event.preventDefault();

            const payload = {
                chapter: parseInt(form.chapter.value, 10),
                summary: form.summary.value,
            };

            prepareGenerationView({ reset: true, scroll: true });
            if (submitButton) {
                submitButton.disabled = true;
            }

            try {
                const result = await postJSON(`/project/${projectId}/generate`, payload);
                if (!result.ok || !result.data.task) {
                    throw new Error(result.data.error || "创建后台任务失败");
                }
                connectGenerationTask(projectId, result.data.task.id, { reset: true, scroll: false, autoRedirect: true });
            } catch (error) {
                alert(error.message);
            } finally {
                if (submitButton) {
                    submitButton.disabled = false;
                }
            }
        });
    }

    function setupRegenerateButtons(projectId, selector, fixedChapterNum = null) {
        document.querySelectorAll(selector).forEach((button) => {
            button.addEventListener("click", async () => {
                const chapterNum = fixedChapterNum || parseInt(button.dataset.regenerate, 10);
                if (!chapterNum) {
                    return;
                }
                if (!confirm(`确定根据第 ${chapterNum} 章内容更新角色状态？`)) {
                    return;
                }

                openProgressDrawer(`第 ${chapterNum} 章状态更新`);
                const statusNode = document.getElementById("progressStatus");
                const logNode = document.getElementById("progressLog");

                try {
                    const response = await fetch(`/project/${projectId}/chapter/${chapterNum}/regenerate`, {
                        method: "POST",
                    });

                    await readSSE(response, (data) => {
                        if (data.type === "status" && statusNode) {
                            statusNode.textContent = data.message;
                            appendLog(logNode, data.message);
                        } else if (data.type === "state_prompt_capture") {
                            appendLog(logNode, `状态更新 Prompt 已保存: ${data.path || "未提供路径"}`, "success");
                        } else if (data.type === "field_update") {
                            renderFieldUpdate(data);
                            appendLog(logNode, `${data.character} -> ${data.field}`, "success");
                        } else if (data.type === "tool_call") {
                            appendLog(logNode, `[工具] ${data.tool_name || "tool"} ${data.character || ""}`);
                        } else if (data.type === "tool_result" || data.type === "agent_note") {
                            appendLog(logNode, data.message || JSON.stringify(data));
                        } else if (data.type === "tool_error" || data.type === "error") {
                            appendLog(logNode, data.message || "发生错误", "error");
                        } else if (data.type === "done") {
                            if (statusNode) {
                                statusNode.textContent = "状态更新完成。";
                            }
                            appendLog(logNode, "状态更新完成。", "success");
                        }
                    });
                } catch (error) {
                    appendLog(logNode, error.message, "error");
                }
            });
        });
    }

    return {
        addFieldRow,
        collectFieldRows,
        deleteCharacter,
        deleteJSON,
        deleteJSONAndReload,
        deleteProject,
        initRipples,
        postJSON,
        setupChapterGeneration,
        setupOutlinePreview,
        setupRegenerateButtons,
    };
})();

document.addEventListener("DOMContentLoaded", () => {
    window.AgentWeb.initRipples();
});
