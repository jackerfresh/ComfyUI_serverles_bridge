import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

app.registerExtension({
    name: "VastServerlessBridge.Hijack",
    async setup() {
        console.log("🔥 [VAST] Загружен!");

        let vastRunning = false;
        const painted = new Map();
        let clearTimer = null;
        let statusEl = null;

        // ── Статус-бар ───────────────────────────────────────────────────────
        statusEl = document.createElement("div");
        Object.assign(statusEl.style, {
            position: "fixed", top: "0", left: "50%",
            transform: "translateX(-50%)",
            background: "rgba(0,0,0,0.85)", color: "#00ff44",
            fontFamily: "monospace", fontSize: "13px",
            padding: "4px 18px", borderRadius: "0 0 8px 8px",
            zIndex: "99999", display: "none",
            border: "1px solid #00ff44", borderTop: "none",
            boxShadow: "0 0 12px #00ff4455", transition: "color 0.3s"
        });
        document.body.appendChild(statusEl);

        function setStatus(text, color = "#00ff44", autoHide = 0) {
            statusEl.style.color = color;
            statusEl.style.borderColor = color;
            statusEl.style.boxShadow = `0 0 12px ${color}55`;
            statusEl.textContent = text;
            statusEl.style.display = "block";
            if (autoHide > 0) setTimeout(hideStatus, autoHide);
        }
        function hideStatus() { statusEl.style.display = "none"; }

        // ── Подсветка нод ────────────────────────────────────────────────────
        function getNode(rawId) {
            if (rawId === null || rawId === undefined) return null;
            return app.graph?.getNodeById(Number(rawId))
                ?? app.graph?.getNodeById(rawId) ?? null;
        }

        function paintNode(rawId, color = "#00ff44") {
            const node = getNode(rawId);
            if (!node) return;
            if (painted.has(node.id)) unpaintNode(node.id);
            const orig = node.onDrawForeground?.bind(node) ?? null;
            painted.set(node.id, orig);
            const _color = color;
            node.onDrawForeground = function(ctx) {
                if (orig) orig(ctx);
                ctx.save();
                ctx.strokeStyle = _color;
                ctx.lineWidth = 3;
                ctx.shadowColor = _color;
                ctx.shadowBlur = 14;
                ctx.strokeRect(-2, -2, this.size[0] + 4, this.size[1] + 4);
                ctx.restore();
            };
            app.graph?.setDirtyCanvas(true, false);
        }

        function unpaintNode(id) {
            const node = getNode(id);
            if (!node || !painted.has(node.id)) return;
            node.onDrawForeground = painted.get(node.id);
            painted.delete(node.id);
        }

        function clearAll() {
            for (const [id] of painted) unpaintNode(id);
            painted.clear();
            app.graph?.setDirtyCanvas(true, true);
        }

        // ── origFetch — сохраняем ДО подмены ────────────────────────────────
        const origFetch = window.fetch.bind(window);

        // ── Перехват window.fetch для Manager ────────────────────────────────
        window.fetch = async function(url, options = {}) {
            const urlStr = typeof url === "string" ? url : url?.url ?? "";

            // Блокируем перезагрузку Manager (чтобы не было "Restarting... [Legacy Mode]")
            // Мы сами управляем рестартом ComfyUI через /kill_comfy
            if (urlStr.includes("/manager/reboot") || urlStr.includes("/api/manager/reboot")
                || (urlStr.includes("restart") && urlStr.includes("manager"))) {
                console.log("🛑 [VAST] Блокируем Manager reboot:", urlStr);
                return new Response(JSON.stringify({ status: "ok", message: "Restart blocked by VAST" }), {
                    status: 200, headers: { "Content-Type": "application/json" }
                });
            }

            // Перехват установки кастомной ноды (Manager V2 web + desktop)
            if (urlStr.includes("/customnode/install") && !urlStr.includes("model")) {
                console.log("🔧 [VAST] Перехват установки ноды:", urlStr, options?.body);
                try {
                    const fwdRes = await origFetch("/vast_install_node", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ git_url: options?.body, endpoint: urlStr })
                    });
                    if (fwdRes.ok) {
                        setStatus("📦 Установка на сервере...", "#00aaff");
                    }
                } catch (e) {
                    console.warn("⚠️ [VAST] Ошибка пересылки:", e);
                }
                return new Response(JSON.stringify({
                    status: "success", message: "Forwarded to Vast",
                    task_id: "vast_install", result: true
                }), { status: 200, headers: { "Content-Type": "application/json" } });
            }

            // Установка модели
            if (urlStr.includes("/manager/model/install") || urlStr.includes("/model/install")) {
                console.log("📥 [VAST] Перехват скачивания модели:", options?.body);
                try {
                    await origFetch("/vast_install_model", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: options?.body ?? "{}"
                    });
                    setStatus("📥 Модель скачивается на сервере...", "#00aaff");
                } catch (e) {
                    console.warn("⚠️ [VAST] Ошибка пересылки модели:", e);
                }
                return new Response(JSON.stringify({ status: "success", result: true }), {
                    status: 200, headers: { "Content-Type": "application/json" }
                });
            }

            return origFetch(url, options);
        };

        // ── Консоль логов сервера ─────────────────────────────────────────────
        // Показывает что происходит на удалённом сервере пока он стартует
        let logPanel = null;
        let logContent = null;
        let logVisible = false;

        function createLogPanel() {
            if (logPanel) return;
            logPanel = document.createElement("div");
            Object.assign(logPanel.style, {
                position: "fixed", bottom: "0", right: "0",
                width: "480px", height: "220px",
                background: "rgba(5,5,15,0.97)", color: "#00ff44",
                fontFamily: "monospace", fontSize: "11px",
                borderTop: "1px solid #00ff4433", borderLeft: "1px solid #00ff4433",
                zIndex: "99990", display: "none", flexDirection: "column",
                borderRadius: "8px 0 0 0"
            });

            const header = document.createElement("div");
            Object.assign(header.style, {
                padding: "4px 10px", background: "rgba(0,30,0,0.8)",
                color: "#00ff44", fontSize: "11px", cursor: "pointer",
                display: "flex", justifyContent: "space-between",
                borderBottom: "1px solid #00ff4422"
            });
            header.innerHTML = `<span>☁️ Vast Server Log</span><span id="vast-log-close" style="color:#555">▼</span>`;
            header.onclick = () => {
                logVisible = !logVisible;
                logPanel.style.display = logVisible ? "flex" : "none";
            };

            logContent = document.createElement("div");
            Object.assign(logContent.style, {
                flex: "1", overflowY: "auto", padding: "6px 10px",
                whiteSpace: "pre-wrap", wordBreak: "break-all"
            });

            logPanel.appendChild(header);
            logPanel.appendChild(logContent);
            document.body.appendChild(logPanel);
        }

        function appendLog(text, color = "#00ff44") {
            if (!logContent) createLogPanel();
            const line = document.createElement("div");
            line.style.color = color;
            line.style.lineHeight = "1.4";
            line.textContent = `[${new Date().toLocaleTimeString()}] ${text}`;
            logContent.appendChild(line);
            // Оставляем последние 200 строк
            while (logContent.children.length > 200) logContent.removeChild(logContent.firstChild);
            logContent.scrollTop = logContent.scrollHeight;
        }

        function showLogPanel() {
            if (!logPanel) createLogPanel();
            logVisible = true;
            logPanel.style.display = "flex";
        }

        function hideLogPanel() {
            if (logPanel) logPanel.style.display = "none";
            logVisible = false;
        }

        // Кнопка открытия лога (маленькая, в правом нижнем углу)
        const logToggleBtn = document.createElement("button");
        logToggleBtn.textContent = "📋 Лог";
        Object.assign(logToggleBtn.style, {
            position: "fixed", bottom: "8px", right: "8px",
            background: "#0a0a1a", color: "#555", border: "1px solid #333",
            borderRadius: "4px", padding: "3px 8px", cursor: "pointer",
            fontFamily: "monospace", fontSize: "11px", zIndex: "99989"
        });
        logToggleBtn.onclick = () => {
            if (logVisible) { hideLogPanel(); logToggleBtn.style.color = "#555"; }
            else { showLogPanel(); logToggleBtn.style.color = "#00ff44"; }
        };
        document.body.appendChild(logToggleBtn);

        // queuePrompt ──────────────────────────────────────────────────────────
        api.queuePrompt = async function(number, { output }) {
            vastRunning = true;
            clearAll();
            showLogPanel();
            
            // Проверяем, есть ли в графе наша кастомная нода для скачивания
            let isSetup = false;
            if (output) {
                for (const key in output) {
                    if (output[key].class_type === "ServerlessSetupNode") {
                        isSetup = true;
                        break;
                    }
                }
            }

            const startMsg = isSetup ? "⏳ Отправляем запрос на скачивание..." : "⏳ Отправляем workflow на сервер...";
            appendLog(startMsg, "#ffaa00");
            logToggleBtn.style.color = "#ffaa00";
            setStatus(startMsg, "#ffaa00");
            
            try {
                const res = await origFetch("/vast_forward", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ prompt: output })
                });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const result = await res.json();
                if (result.status === "error") throw new Error(result.message);
                
                const successMsg = isSetup ? "🔄 Идет скачивание файлов на сервере..." : "🔄 Генерация запущена...";
                appendLog(successMsg, "#00aaff");
                setStatus(successMsg, "#00aaff");
                return { prompt_id: "vast_job_from_ui", number, node_errors: {} };
            } catch (err) {
                vastRunning = false;
                appendLog(`❌ Ошибка: ${err.message}`, "#ff4444");
                logToggleBtn.style.color = "#ff4444";
                setStatus(`❌ ${err.message}`, "#ff4444", 6000);
                return { prompt_id: "error", number, node_errors: {} };
            }
        };

        // ── Interrupt ────────────────────────────────────────────────────────
        api.interrupt = async function() {
            if (!vastRunning) return;
            setStatus("🛑 Прерывание...", "#ffaa00");
            try {
                await origFetch("/vast_interrupt", { method: "POST" });
            } catch (err) {
                setStatus(`❌ ${err.message}`, "#ff4444", 4000);
            }
        };

        // ── Executing ────────────────────────────────────────────────────────
        api.addEventListener("executing", (event) => {
            if (!vastRunning) return;
            const rawId = event.detail?.node ?? event.detail?.node_id ?? null;
            if (clearTimer) { clearTimeout(clearTimer); clearTimer = null; }
            if (rawId === null) {
                clearTimer = setTimeout(() => { clearAll(); clearTimer = null; }, 1000);
                return;
            }
            clearAll();
            paintNode(rawId, "#00ff44");
            const node = getNode(rawId);
            setStatus(`⚡ ${node?.type ?? rawId}`, "#00ff44");
        });

        // ── Progress ─────────────────────────────────────────────────────────
        api.addEventListener("progress", (event) => {
            if (!vastRunning) return;
            const { value, max, node } = event.detail || {};
            if (node !== undefined && max > 0) {
                const n = getNode(node);
                if (n) {
                    n.progress = value / max;
                    app.graph?.setDirtyCanvas(true, false);
                    setStatus(`⚡ ${n.type ?? node}  ${value}/${max}  (${Math.round(value/max*100)}%)`, "#00ff44");
                }
            }
        });

        api.addEventListener("executed", (event) => {
            if (!vastRunning) return;
            const n = getNode(event.detail?.node ?? event.detail?.node_id);
            if (n) n.progress = null;
        });

        // ── Ошибки ───────────────────────────────────────────────────────────
        api.addEventListener("execution_error", (event) => {
            const detail = event.detail;
            console.error("❌ [VAST] execution_error:", detail);
            vastRunning = false;
            clearAll();
            const nodeId = detail?.node_id ?? detail?.node;
            if (nodeId !== undefined && nodeId !== null) {
                paintNode(nodeId, "#ff3333");
                setTimeout(() => { unpaintNode(nodeId); app.graph?.setDirtyCanvas(true, true); }, 8000);
            }
            const msg = detail?.exception_message ?? detail?.error ?? "Ошибка выполнения";
            const nodeType = detail?.node_type ?? "?";
            // Показываем полный лог без обрезки — важная информация для отладки
            appendLog(`❌ Ошибка ноды ${nodeId} (${nodeType}):\n${msg}`, "#ff4444");
            logToggleBtn.style.color = "#ff4444";
            // Для статус-бара показываем короткую версию
            const statusMsg = msg.length > 80 ? msg.substring(0, 80) + "..." : msg;
            setStatus(`❌ ${statusMsg}`, "#ff3333", 8000);
        });

        api.addEventListener("workflow_error", (event) => {
            console.error("❌ [VAST] workflow_error:", event.detail);
            vastRunning = false;
            const errMsg = event.detail?.error ?? "Ошибка воркфлоу";
            
            let validationNodes = [];
            let logMsg = errMsg;
            
            try {
                // Пытаемся распарсить JSON, если это ошибка валидации (400 Bad Request)
                const jsonMatch = errMsg.match(/ComfyUI API Error \d+: (\{.*\})$/s);
                if (jsonMatch) {
                    const errData = JSON.parse(jsonMatch[1]);
                    if (errData.node_errors) {
                        // Формируем читаемое сообщение вместо огромного JSON
                        const nodeErrors = [];
                        for (const nodeId in errData.node_errors) {
                            validationNodes.push(nodeId);
                            paintNode(nodeId, "#ff3333");
                            setTimeout(() => { unpaintNode(nodeId); app.graph?.setDirtyCanvas(true, true); }, 8000);
                            
                            const nodeErr = errData.node_errors[nodeId];
                            const nodeType = nodeErr.class_type || "?";
                            const errors = nodeErr.errors || [];
                            const errTexts = errors.map(e => e.details || e.message || "unknown").join(", ");
                            nodeErrors.push(`Нода ${nodeId} (${nodeType}): ${errTexts}`);
                        }
                        logMsg = `❌ Ошибка валидации:\n${nodeErrors.join("\n")}`;
                    }
                }
            } catch(e) {
                console.warn("[VAST] Failed to parse validation error:", e);
            }

            // Если ошибка пришла сразу после execution_error ИЛИ мы подсветили битые ноды валидации — не стираем красную обводку
            if (!errMsg.includes("ComfyUI error:") && validationNodes.length === 0) {
                clearAll();
            }
            
            // Для обычных ошибок (не validation) — НЕ обрезаем, показываем полный лог
            // (пользователь хочет видеть весь traceback для отладки)
            
            appendLog(logMsg, "#ff4444");
            logToggleBtn.style.color = "#ff4444";
            
            // Для статус-бара показываем короткую версию
            const statusMsg = validationNodes.length > 0 
                ? `❌ Ошибка валидации в ${validationNodes.length} нод(ах)`
                : (logMsg.length > 80 ? logMsg.substring(0, 80) + "..." : logMsg);
            setStatus(statusMsg, "#ff3333", 5000);
        });

        // ── Done ─────────────────────────────────────────────────────────────
        api.addEventListener("workflow_done", () => {
            vastRunning = false;
            if (clearTimer) clearTimeout(clearTimer);
            clearTimer = setTimeout(() => { clearAll(); clearTimer = null; }, 1000);
            appendLog("✅ Workflow завершён!", "#00ff44");
            logToggleBtn.style.color = "#00ff44";
            setStatus("✅ Готово!", "#00ff44", 3000);
        });

        // ── Логи сервера → консоль ───────────────────────────────────────────
        api.addEventListener("vast_log_message", (e) => {
            const text = e.detail?.text?.trim();
            if (text) {
                console.log("☁️ [VAST]:", text);
                appendLog(text, "#aaffaa");
                
                // Показываем важные статусы в статус-баре
                if (text.includes("Requested to load") || 
                    text.includes("loaded completely") ||
                    text.includes("loaded partially") ||
                    text.includes("Unloaded") ||
                    text.match(/\d+%\|/)) {  // прогресс-бар типа "35%|███"
                    setStatus(`⚙️ ${text.substring(0, 60)}`, "#00aaff");
                }
            }
        });

        api.addEventListener("comfy_status", (e) => {
            const status = e.detail?.status;
            if (status === "starting") {
                appendLog("🔄 ComfyUI запускается на сервере...", "#ffaa00");
                showLogPanel();
                logToggleBtn.style.color = "#ffaa00";
            } else if (status === "ready") {
                appendLog("✅ ComfyUI готов!", "#00ff44");
                logToggleBtn.style.color = "#00ff44";
            }
        });

        // ── Прогресс установки ────────────────────────────────────────────────
        api.addEventListener("vast_install_progress", (e) => {
            const text = e.detail?.text ?? "Установка...";
            appendLog(`📦 ${text}`, "#00aaff");
            setStatus(`📦 ${text}`, "#00aaff");
        });

        // ── Установка завершена ──────────────────────────────────────────────
        // НЕ делаем auto-reload — ноды уже зарегистрированы в памяти ComfyUI
        // Пользователь сам решает когда обновить страницу
        api.addEventListener("vast_install_done", (e) => {
            const text  = e.detail?.text ?? "✅ Готово!";
            const count = e.detail?.count ?? 0;
            console.log("✅ [VAST] install_done:", e.detail);

            if (count > 0) {
                // Ноды добавлены — показываем кнопку перезагрузки
                // Браузер нужно обновить чтобы ноды появились в меню Add Node
                statusEl.innerHTML = "";
                const msg = document.createElement("span");
                msg.textContent = `${text} — `;
                const btn = document.createElement("span");
                btn.textContent = "Обновить меню нод";
                btn.style.cssText = "cursor:pointer;text-decoration:underline;";
                btn.onclick = () => location.reload();
                statusEl.appendChild(msg);
                statusEl.appendChild(btn);
                statusEl.style.color = "#00ff44";
                statusEl.style.borderColor = "#00ff44";
                statusEl.style.display = "block";
                // Автогасим через 15 сек
                setTimeout(() => {
                    statusEl.innerHTML = "";
                    hideStatus();
                }, 15000);
            } else {
                setStatus(text, "#00ff44", 5000);
            }

            // Обновляем заглушки моделей в фоне
            origFetch("/vast_sync_models").catch(() => {});
        });

        // ── Interrupt events ──────────────────────────────────────────────────
        api.addEventListener("vast_interrupt_done", (e) => {
            vastRunning = false;
            clearAll();
            setStatus(e.detail?.text ?? "✅ Прервано!", "#00ff44", 3000);
        });

        api.addEventListener("vast_interrupt_error", (e) => {
            setStatus(e.detail?.text ?? "❌ Ошибка прерывания", "#ff4444", 5000);
        });
    }
});


// ═══════════════════════════════════════════════════════════════════════════════
// ☁️ VAST NODE MANAGER — панель управления нодами
// ═══════════════════════════════════════════════════════════════════════════════

(function() {
    function addVastManagerButton() {
        const tryAdd = () => {
            const toolbar = document.querySelector(".comfyui-menu-right, .comfyui-menu, nav");
            if (!toolbar) { setTimeout(tryAdd, 500); return; }
            
            // Статус подключения
            const badge = document.createElement("div");
            badge.id = "vast-connection-badge";
            Object.assign(badge.style, {
                background: "#1a1a2e", border: "1px solid #555", borderRadius: "6px",
                padding: "4px 10px", fontFamily: "monospace", fontSize: "12px",
                marginLeft: "8px", display: "flex", alignItems: "center", gap: "6px"
            });
            badge.innerHTML = `<div id="vast-dot" style="width:8px;height:8px;border-radius:50%;background:gray"></div><span id="vast-text" style="color:#aaa">Ожидание...</span>`;
            toolbar.appendChild(badge);

            const btn = document.createElement("button");
            btn.textContent = "☁️ Vast Nodes";
            Object.assign(btn.style, {
                background: "#1a1a2e", color: "#00ff44",
                border: "1px solid #00ff44", borderRadius: "6px",
                padding: "4px 12px", cursor: "pointer",
                fontFamily: "monospace", fontSize: "12px",
                marginLeft: "8px",
            });
            btn.onclick = openVastNodeManager;
            toolbar.appendChild(btn);
            
            // Пинг статуса каждые 15 секунд (чтобы не спамить в консоль)
            setInterval(async () => {
                try {
                    const res = await fetch("/vast_ping");
                    if (!res.ok) throw new Error();
                    const data = await res.json();
                    if (data.status === "online") {
                        document.getElementById("vast-dot").style.background = "#00ff44";
                        document.getElementById("vast-dot").style.boxShadow = "0 0 8px #00ff44";
                        document.getElementById("vast-text").style.color = "#00ff44";
                        document.getElementById("vast-text").textContent = "Подключено к Vast";
                        badge.style.borderColor = "#00ff44";
                    } else {
                        document.getElementById("vast-dot").style.background = "#ff4444";
                        document.getElementById("vast-dot").style.boxShadow = "none";
                        document.getElementById("vast-text").style.color = "#ff4444";
                        document.getElementById("vast-text").textContent = "Vast Отключен";
                        badge.style.borderColor = "#ff4444";
                    }
                } catch(e) {
                    document.getElementById("vast-dot").style.background = "gray";
                    document.getElementById("vast-dot").style.boxShadow = "none";
                    document.getElementById("vast-text").style.color = "gray";
                    document.getElementById("vast-text").textContent = "Нет связи";
                    badge.style.borderColor = "#555";
                }
            }, 15000);
        };
        setTimeout(tryAdd, 1500);
    }

    let modal = null;

    function openVastNodeManager() {
        if (modal) { modal.remove(); modal = null; }

        const overlay = document.createElement("div");
        Object.assign(overlay.style, {
            position: "fixed", inset: "0",
            background: "rgba(0,0,0,0.7)", zIndex: "999998",
        });
        overlay.onclick = (e) => { if (e.target === overlay) closeModal(); };

        modal = document.createElement("div");
        Object.assign(modal.style, {
            position: "fixed", top: "50%", left: "50%",
            transform: "translate(-50%, -50%)",
            background: "#1a1a2e", color: "#e0e0e0",
            border: "1px solid #00ff44", borderRadius: "10px",
            padding: "20px", width: "540px", maxHeight: "80vh",
            overflowY: "auto", zIndex: "999999",
            fontFamily: "monospace", boxShadow: "0 0 30px #00ff4444"
        });

        modal.innerHTML = `
            <div style="font-size:16px;color:#00ff44;margin-bottom:14px;display:flex;justify-content:space-between;align-items:center">
                <span>☁️ Vast Server Nodes</span>
                <div style="display:flex;gap:8px;align-items:center">
                    <button id="vast-sync-btn"
                        style="background:#001133;color:#00aaff;border:1px solid #00aaff;border-radius:4px;
                               padding:3px 10px;cursor:pointer;font-family:monospace;font-size:11px"
                        title="Скачать ноды с сервера в манифест">
                        ⬇️ Скачать с сервера
                    </button>
                    <span id="vast-close" style="cursor:pointer;color:#888;font-size:20px">✕</span>
                </div>
            </div>
            <div id="vast-node-list">
                <div style="color:#888;text-align:center;padding:20px">⏳ Загружаем...</div>
            </div>
            <div style="margin-top:16px;border-top:1px solid #333;padding-top:14px">
                <div style="color:#aaa;font-size:12px;margin-bottom:8px">📦 Установить ноду (git URL):</div>
                <div style="display:flex;gap:8px">
                    <input id="vast-install-url" type="text"
                        placeholder="https://github.com/author/ComfyUI-NodePack"
                        style="flex:1;background:#0d0d1a;color:#e0e0e0;border:1px solid #333;
                               border-radius:4px;padding:6px 10px;font-family:monospace;font-size:12px;outline:none"/>
                    <button id="vast-install-btn"
                        style="background:#003311;color:#00ff44;border:1px solid #00ff44;
                               border-radius:4px;padding:6px 14px;cursor:pointer;font-family:monospace">
                        Install
                    </button>
                </div>
                <div id="vast-install-status" style="color:#888;font-size:11px;margin-top:6px;min-height:16px"></div>
            </div>
        `;

        overlay.appendChild(modal);
        document.body.appendChild(overlay);

        document.getElementById("vast-close").onclick = closeModal;
        document.getElementById("vast-install-btn").onclick = () => {
            const url = document.getElementById("vast-install-url").value.trim();
            if (url) installNode(url);
        };
        document.getElementById("vast-install-url").addEventListener("keydown", (e) => {
            if (e.key === "Enter") document.getElementById("vast-install-btn").click();
        });

        // Кнопка "Скачать с сервера"
        document.getElementById("vast-sync-btn").onclick = async () => {
            const btn = document.getElementById("vast-sync-btn");
            btn.disabled = true;
            btn.textContent = "⏳ Синкаем...";
            try {
                const resp = await fetch("/vast_sync_nodes");
                const data = await resp.json();
                if (data.count > 0) {
                    btn.textContent = `✅ +${data.count} нод`;
                    btn.style.color = "#00ff44";
                    btn.style.borderColor = "#00ff44";
                    setTimeout(() => {
                        if (confirm(`Скачано ${data.count} новых нод. Перезагрузить меню?`)) {
                            location.reload();
                        }
                    }, 500);
                } else {
                    btn.textContent = "✅ Всё актуально";
                    setTimeout(() => {
                        btn.textContent = "⬇️ Скачать с сервера";
                        btn.disabled = false;
                    }, 3000);
                }
                loadNodes();
            } catch (e) {
                btn.textContent = "❌ Ошибка";
                btn.disabled = false;
            }
        };

        loadNodes();

        function closeModal() { overlay.remove(); modal = null; }
    }

    async function loadNodes() {
        const listEl = document.getElementById("vast-node-list");
        if (!listEl) return;
        try {
            const resp = await fetch("/vast_server_nodes_list");
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();

            const allNodes = data.nodes || [];

            if (allNodes.length === 0) {
                listEl.innerHTML = `<div style="color:#888;text-align:center;padding:20px">Нет установленных нод</div>`;
                return;
            }

            listEl.innerHTML = `<div style="color:#888;font-size:11px;margin-bottom:10px">Установлено: ${allNodes.length} пак(ов)</div>`;

            for (const info of allNodes) {
                const pack       = info.name;
                const onServer   = info.on_server;
                const inManifest = info.in_manifest;

                const row = document.createElement("div");
                Object.assign(row.style, {
                    display: "flex", justifyContent: "space-between", alignItems: "center",
                    padding: "8px 10px", marginBottom: "6px",
                    background: "#0d0d1a", borderRadius: "6px",
                    border: `1px solid ${onServer ? "#1a3a1a" : "#3a2a00"}`
                });

                const nameEl = document.createElement("div");
                nameEl.style.fontSize = "13px";
                let badges = "";
                if (onServer)   badges += ` <span style="color:#00aa44;font-size:10px">☁️ сервер</span>`;
                if (inManifest) badges += ` <span style="color:#555;font-size:10px">📝 локально</span>`;
                nameEl.innerHTML = `<span style="color:#00ff44">${pack}</span>${badges}`;

                const delBtn = document.createElement("button");
                delBtn.textContent = "🗑";
                Object.assign(delBtn.style, {
                    background: "transparent", color: "#ff4444",
                    border: "1px solid #ff4444", borderRadius: "4px",
                    padding: "2px 8px", cursor: "pointer",
                    fontFamily: "monospace", fontSize: "11px"
                });
                delBtn.onclick = () => uninstallNode(pack, delBtn, row);

                row.appendChild(nameEl);
                row.appendChild(delBtn);
                listEl.appendChild(row);
            }
        } catch (err) {
            listEl.innerHTML = `<div style="color:#ff4444;text-align:center;padding:20px">❌ ${err.message}</div>`;
        }
    }

    async function installNode(gitUrl) {
        const statusEl = document.getElementById("vast-install-status");
        const btn      = document.getElementById("vast-install-btn");
        if (!statusEl || !btn) return;
        btn.disabled = true;
        btn.textContent = "⏳...";
        statusEl.style.color = "#00aaff";
        statusEl.textContent = "Отправляем на сервер...";
        try {
            const resp = await fetch("/vast_install_node", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ git_url: gitUrl })
            });
            const data = await resp.json();
            if (resp.ok && data.status === "ok") {
                statusEl.style.color = "#00ff44";
                statusEl.textContent = "✅ Установка запущена, ожидайте...";
                document.getElementById("vast-install-url").value = "";
                setTimeout(loadNodes, 5000);
            } else {
                statusEl.style.color = "#ff4444";
                statusEl.textContent = `❌ ${data.message ?? "Ошибка"}`;
            }
        } catch (err) {
            statusEl.style.color = "#ff4444";
            statusEl.textContent = `❌ ${err.message}`;
        } finally {
            btn.disabled = false;
            btn.textContent = "Install";
        }
    }

    async function uninstallNode(packName, btn, row) {
        if (!confirm(`Удалить "${packName}" с сервера и из манифеста?`)) return;
        btn.disabled = true;
        btn.textContent = "⏳...";
        try {
            const resp = await fetch("/vast_uninstall_server_node", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ pack_name: packName })
            });
            const data = await resp.json();
            if (resp.ok && data.status === "ok") {
                row.style.opacity = "0.4";
                row.style.textDecoration = "line-through";
                btn.textContent = "✅";
            } else {
                btn.textContent = "❌";
                btn.disabled = false;
            }
        } catch (err) {
            btn.textContent = "❌";
            btn.disabled = false;
        }
    }

    // ── Авто-синк при загрузке (без reload!) ────────────────────────────────
    async function autoSyncOnLoad() {
        try {
            const resp = await fetch("/vast_sync_nodes");
            if (!resp.ok) return;
            const data = await resp.json();
            if (data.reload_required && data.count > 0) {
                const toast = document.createElement("div");
                Object.assign(toast.style, {
                    position: "fixed", bottom: "20px", right: "20px",
                    background: "#1a1a2e", color: "#00ff44",
                    border: "1px solid #00ff44", borderRadius: "8px",
                    padding: "10px 16px", fontFamily: "monospace", fontSize: "12px",
                    zIndex: "999990", boxShadow: "0 0 16px #00ff4444", cursor: "pointer"
                });
                toast.innerHTML = `☁️ +${data.count} нод с сервера.<br><span style="text-decoration:underline">Обновить меню нод</span>`;
                toast.onclick = () => location.reload();
                document.body.appendChild(toast);
                setTimeout(() => toast.remove(), 12000);
            }
        } catch (e) { /* Сервер недоступен — нормально */ }
    }
    setTimeout(autoSyncOnLoad, 3000);

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", addVastManagerButton);
    } else {
        setTimeout(addVastManagerButton, 1000);
    }
})();
