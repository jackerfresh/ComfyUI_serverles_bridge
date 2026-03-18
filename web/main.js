import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// Создаем переменные для нашего терминала
let vastTerminal = null;
let vastTerminalContent = null;

// Функция для отрисовки хакерского окна
function initVastTerminal() {
    if (vastTerminal) return; // Если уже открыт - пропускаем
    
    vastTerminal = document.createElement("div");
    Object.assign(vastTerminal.style, {
        position: "fixed",
        bottom: "20px",
        right: "20px",
        width: "600px",
        height: "400px",
        backgroundColor: "rgba(0, 0, 0, 0.9)",
        color: "#0f0", // Зеленый текст хакера
        fontFamily: "monospace",
        fontSize: "12px",
        padding: "15px",
        paddingTop: "30px",
        borderRadius: "8px",
        border: "1px solid #0f0",
        overflowY: "auto",
        zIndex: "9999",
        display: "none",
        boxShadow: "0px 0px 15px rgba(0, 255, 0, 0.2)"
    });

    // Кнопка закрытия окна
    const closeBtn = document.createElement("button");
    closeBtn.innerText = "X";
    Object.assign(closeBtn.style, {
        position: "absolute",
        top: "5px",
        right: "10px",
        background: "none",
        color: "#f00",
        border: "none",
        cursor: "pointer",
        fontWeight: "bold",
        fontSize: "16px"
    });
    closeBtn.onclick = () => vastTerminal.style.display = "none";
    vastTerminal.appendChild(closeBtn);

    const title = document.createElement("div");
    title.innerHTML = "<b style='color:#fff;'>🔥 VAST.AI SERVERLESS TERMINAL</b><br><hr style='border-color:#0f0;'>";
    vastTerminal.appendChild(title);

    vastTerminalContent = document.createElement("div");
    vastTerminalContent.style.whiteSpace = "pre-wrap"; // Сохраняем переносы строк
    vastTerminal.appendChild(vastTerminalContent);

    document.body.appendChild(vastTerminal);
}

app.registerExtension({
    name: "VastServerlessBridge.Hijack",
    async setup() {
        console.log("🔥 Vast Serverless Bridge JS загружен! Ждем логи...");

        // 1. ПЕРЕХВАТ КНОПКИ QUEUE (осталось как было)
        api.queuePrompt = async function(number, { output, workflow }) {
            console.log("🚀 Отправляем задачу на Vast.ai...");
            try {
                const res = await fetch("/vast_forward", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ prompt: output })
                });

                if (!res.ok) throw new Error(`Ошибка сервера: ${res.status}`);
                const result = await res.json();
                
                return { prompt_id: result.task_id || "serverless_task", number: number, node_errors: {} };
            } catch (error) {
                console.error("❌ Ошибка при отправке на Vast:", error);
                alert("Ошибка отправки! Запусти туннель lhr.life!");
                return { prompt_id: "error", number: number, node_errors: {} };
            }
        };

        // 2. СЛУШАЕМ ЛОГИ С СЕРВЕРА (ВОТ ОНА МАГИЯ!)
        api.addEventListener("vast_log_message", (event) => {
            initVastTerminal();
            vastTerminal.style.display = "block"; // Показываем окно
            
            // Добавляем строчку лога в терминал
            const textNode = document.createTextNode(event.detail.text);
            vastTerminalContent.appendChild(textNode);
            
            // Автоматически скроллим вниз (как в настоящей консоли)
            vastTerminal.scrollTop = vastTerminal.scrollHeight;
        });
    }
});
