import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// Переменные для нашего хакерского терминала
let vastTerminal = null;
let vastTerminalContent = null;

// Функция отрисовки терминала
function initVastTerminal() {
    if (vastTerminal) return; 
    
    vastTerminal = document.createElement("div");
    Object.assign(vastTerminal.style, {
        position: "fixed",
        bottom: "20px",
        right: "20px",
        width: "650px",
        height: "450px",
        backgroundColor: "rgba(10, 10, 10, 0.95)",
        color: "#0f0", // Зеленый хакерский цвет
        fontFamily: "monospace",
        fontSize: "13px",
        padding: "15px",
        paddingTop: "35px",
        borderRadius: "8px",
        border: "1px solid #0f0",
        overflowY: "auto",
        zIndex: "9999",
        display: "none",
        boxShadow: "0px 0px 20px rgba(0, 255, 0, 0.3)"
    });

    // Кнопка закрытия
    const closeBtn = document.createElement("button");
    closeBtn.innerText = "✖ ЗАКРЫТЬ";
    Object.assign(closeBtn.style, {
        position: "absolute",
        top: "5px",
        right: "10px",
        background: "none",
        color: "#ff3333",
        border: "none",
        cursor: "pointer",
        fontWeight: "bold",
        fontSize: "14px"
    });
    closeBtn.onclick = () => vastTerminal.style.display = "none";
    vastTerminal.appendChild(closeBtn);

    // Заголовок
    const title = document.createElement("div");
    title.innerHTML = "<b style='color:#fff;'>🔥 VAST.AI SERVERLESS TERMINAL</b><br><hr style='border-color:#0f0;'>";
    vastTerminal.appendChild(title);

    // Контейнер для текста
    vastTerminalContent = document.createElement("div");
    vastTerminalContent.style.whiteSpace = "pre-wrap"; 
    vastTerminal.appendChild(vastTerminalContent);

    document.body.appendChild(vastTerminal);
}

app.registerExtension({
    name: "VastServerlessBridge.Hijack",
    async setup() {
        console.log("🔥 Vast Serverless JS загружен! Слушаем логи...");

        // 1. ПЕРЕХВАТ КНОПКИ QUEUE (Блокируем локальный рендер и шлем на Васт)
        api.queuePrompt = async function(number, { output, workflow }) {
            console.log("🚀 Отправляем задачу на Vast.ai...");
            
            // Очищаем терминал перед новым запуском
            if (vastTerminalContent) vastTerminalContent.innerHTML = "";
            
            try {
                const res = await fetch("/vast_forward", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ prompt: output })
                });

                if (!res.ok) throw new Error(`Ошибка сервера: ${res.status}`);
                const result = await res.json();
                
                // Возвращаем фейковый ответ Комфи, чтобы он начал крутить зеленую рамку
                return { prompt_id: result.task_id || "vast_task", number: number, node_errors: {} };
            } catch (error) {
                console.error("❌ Ошибка отправки:", error);
                alert("Ошибка отправки! Проверь консоль run_cpu.bat");
                return { prompt_id: "error", number: number, node_errors: {} };
            }
        };

        // 2. СЛУШАЕМ ЛОГИ С СЕРВЕРА В РЕАЛЬНОМ ВРЕМЕНИ
        api.addEventListener("vast_log_message", (event) => {
            initVastTerminal();
            vastTerminal.style.display = "block"; // Показываем окно
            
            // Добавляем строчку
            const textNode = document.createTextNode(event.detail.text);
            vastTerminalContent.appendChild(textNode);
            
            // Скроллим в самый низ, как в настоящей консоли
            vastTerminal.scrollTop = vastTerminal.scrollHeight;
        });
    }
});