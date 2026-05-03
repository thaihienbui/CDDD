from flask import Flask, render_template_string, request, jsonify
import time
import threading
import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()  # Load biến môi trường từ .env

app = Flask(__name__)

# ================== CẤU HÌNH ==================
API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    print("⚠️  CẢNH BÁO: Chưa set GEMINI_API_KEY trong .env")

genai.configure(api_key=API_KEY)

model = genai.GenerativeModel(
    model_name="gemini-2.5-flash",
    system_instruction="""
    Bạn là Chatbot Điện học thông minh, hỗ trợ học sinh tìm hiểu về điện.

    Nhiệm vụ:
    - Giải thích các khái niệm: cường độ dòng điện (I), điện áp (U), công suất (P), điện trở (R), nhiệt lượng (Q)
    - Hệ thống có 1 cảm biến dòng (I) và 2 cảm biến điện áp (U1, U2)
    - Từ đó tính: P1=I*U1, R1=U1/I, Q1=P1*t và P2=I*U2, R2=U2/I, Q2=P2*t
    - Giải thích ý nghĩa các số liệu đo được
    - Trả lời ngắn gọn, dễ hiểu, phù hợp học sinh THPT

    Phong cách: thân thiện, dễ hiểu, có ví dụ thực tế.
    Nếu không chắc: "Bạn nên kiểm tra thêm tài liệu vật lý hoặc hỏi giáo viên nhé!"
    """
)

chat_session = model.start_chat(history=[])

# ================== LƯU DỮ LIỆU ==================
latest_data = {"I": 0.0, "U1": 0.0, "U2": 0.0, "V": 0.0, "timestamp": ""}
history_data = {
    "I": [], "U1": [], "U2": [],
    "R1": [], "R2": [],
    "Q1": [], "Q2": [],
    "timestamps": []
}
Q1_total = 0.0
Q2_total = 0.0
last_recv_time = None
MAX_HISTORY = 60
data_lock = threading.Lock()

# ================== HTML ==================
HTML = '''
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>⚡ Đo Điện ESP32-S3</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Rajdhani:wght@400;500;600&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        :root {
            --cyan:   #00e5ff;
            --green:  #00ff9d;
            --pink:   #ff2d78;
            --yellow: #ffe600;
            --orange: #ff8c00;
            --purple: #bf5fff;
            --teal:   #00ffc8;
            --red:    #ff4f4f;
            --bg-dark:  #030a1a;
            --bg-panel: rgba(5,15,40,0.92);
            --sidebar-w: 220px;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background-color: var(--bg-dark);
            background-image:
                radial-gradient(ellipse at 20% 50%, rgba(0,60,120,0.4) 0%, transparent 60%),
                radial-gradient(ellipse at 80% 20%, rgba(0,80,60,0.25) 0%, transparent 50%),
                radial-gradient(ellipse at 60% 80%, rgba(80,0,80,0.2) 0%, transparent 50%);
            color: #c8e6ff;
            font-family: 'Rajdhani', sans-serif;
            min-height: 100vh;
            display: flex;
            overflow-x: hidden;
        }

        /* SIDEBAR */
        #sidebar {
            width: var(--sidebar-w); min-height: 100vh;
            background: linear-gradient(180deg,rgba(0,10,30,.98),rgba(0,20,50,.95));
            border-right: 1px solid rgba(0,229,255,.2);
            display: flex; flex-direction: column;
            position: fixed; top:0; left:0; z-index:100;
            box-shadow: 4px 0 30px rgba(0,229,255,.1);
        }
        .sidebar-logo { padding:28px 20px 24px; border-bottom:1px solid rgba(0,229,255,.15); text-align:center; }
        .sidebar-logo .logo-icon { font-size:2.5rem; display:block; margin-bottom:8px; filter:drop-shadow(0 0 12px var(--yellow)); animation:pulse 2s ease-in-out infinite; }
        @keyframes pulse { 0%,100%{transform:scale(1);filter:drop-shadow(0 0 12px var(--yellow))} 50%{transform:scale(1.1);filter:drop-shadow(0 0 20px var(--yellow))} }
        .sidebar-logo h2 { font-family:'Orbitron',monospace; font-size:.72rem; font-weight:700; color:var(--cyan); letter-spacing:2px; text-transform:uppercase; line-height:1.5; }
        .sidebar-logo p { font-size:.68rem; color:rgba(200,230,255,.45); margin-top:4px; letter-spacing:1px; }
        .sidebar-nav { flex:1; padding:20px 0; }
        .nav-label { font-size:.6rem; letter-spacing:3px; text-transform:uppercase; color:rgba(200,230,255,.3); padding:0 20px 10px; margin-top:10px; }
        .nav-item { display:flex; align-items:center; gap:12px; padding:14px 20px; cursor:pointer; transition:all .25s; border-left:3px solid transparent; color:rgba(200,230,255,.6); font-size:.95rem; font-weight:500; letter-spacing:.5px; text-decoration:none; }
        .nav-item:hover { background:rgba(0,229,255,.06); color:var(--cyan); border-left-color:rgba(0,229,255,.4); }
        .nav-item.active { background:rgba(0,229,255,.1); color:var(--cyan); border-left-color:var(--cyan); }
        .nav-item .nav-icon { font-size:1.1rem; width:22px; text-align:center; }
        .sidebar-footer { padding:16px 20px; border-top:1px solid rgba(0,229,255,.1); font-size:.65rem; color:rgba(200,230,255,.3); text-align:center; letter-spacing:1px; }

        /* MAIN */
        #main { margin-left:var(--sidebar-w); flex:1; padding:30px; min-height:100vh; }
        .page { display:none; }
        .page.active { display:block; }
        .page-header { margin-bottom:28px; padding-bottom:18px; border-bottom:1px solid rgba(0,229,255,.15); }
        .page-header h1 { font-family:'Orbitron',monospace; font-size:1.3rem; font-weight:700; color:var(--cyan); letter-spacing:3px; text-transform:uppercase; margin-bottom:4px; text-shadow:0 0 20px rgba(0,229,255,.5); }
        .page-header p { font-size:.85rem; color:rgba(200,230,255,.45); letter-spacing:1px; }

        /* PANEL */
        .panel { background:var(--bg-panel); border:1px solid rgba(0,229,255,.15); border-radius:16px; padding:24px; backdrop-filter:blur(12px); box-shadow:0 8px 32px rgba(0,0,0,.4),inset 0 1px 0 rgba(255,255,255,.05); margin-bottom:22px; }

        /* STATUS */
        .status-bar { display:flex; align-items:center; gap:16px; padding:14px 20px; background:rgba(0,229,255,.04); border:1px solid rgba(0,229,255,.12); border-radius:12px; margin-bottom:22px; }
        .status-dot { width:8px; height:8px; border-radius:50%; background:var(--green); box-shadow:0 0 8px var(--green); animation:blink 1.5s ease-in-out infinite; }
        .status-dot.offline { background:#ff4444; box-shadow:0 0 8px #ff4444; animation:none; }
        @keyframes blink { 0%,100%{opacity:1} 50%{opacity:.3} }
        .status-text { font-size:.82rem; color:rgba(200,230,255,.6); letter-spacing:1px; }
        .status-time { font-family:'Orbitron',monospace; font-size:.72rem; color:rgba(200,230,255,.35); margin-left:auto; }

        /* METRIC CARDS */
        .metric-cards { display:grid; grid-template-columns:repeat(3,1fr); gap:16px; margin-bottom:22px; }
        .metric-card { background:var(--bg-panel); border-radius:18px; padding:22px 18px; border:1px solid rgba(0,229,255,.15); position:relative; overflow:hidden; backdrop-filter:blur(10px); transition:transform .2s,box-shadow .2s; }
        .metric-card:hover { transform:translateY(-4px); box-shadow:0 16px 40px rgba(0,0,0,.5); }
        .metric-card::before { content:''; position:absolute; top:0;left:0;right:0; height:3px; }
        .card-I::before   { background:linear-gradient(90deg,var(--cyan),transparent); }
        .card-U1::before  { background:linear-gradient(90deg,var(--yellow),transparent); }
        .card-U2::before  { background:linear-gradient(90deg,var(--purple),transparent); }
        .metric-card .glow-bg { position:absolute; width:110px;height:110px; border-radius:50%; opacity:.08; top:-20px;right:-20px; }
        .card-I  .glow-bg  { background:var(--cyan); }
        .card-U1 .glow-bg  { background:var(--yellow); }
        .card-U2 .glow-bg  { background:var(--purple); }
        .metric-label { font-size:.7rem; letter-spacing:3px; text-transform:uppercase; margin-bottom:8px; font-weight:600; }
        .card-I  .metric-label { color:var(--cyan); }
        .card-U1 .metric-label { color:var(--yellow); }
        .card-U2 .metric-label { color:var(--purple); }
        .metric-name { font-size:.72rem; color:rgba(200,230,255,.45); margin-bottom:12px; letter-spacing:1px; }
        .metric-value { font-family:'Orbitron',monospace; font-size:2rem; font-weight:700; line-height:1; margin-bottom:6px; }
        .card-I  .metric-value { color:var(--cyan);   text-shadow:0 0 20px rgba(0,229,255,.6); }
        .card-U1 .metric-value { color:var(--yellow); text-shadow:0 0 20px rgba(255,230,0,.6); }
        .card-U2 .metric-value { color:var(--purple); text-shadow:0 0 20px rgba(191,95,255,.6); }
        .metric-unit { font-size:.72rem; color:rgba(200,230,255,.4); letter-spacing:2px; }

        /* CALC GRID 3x2 */
        .calc-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:14px; }
        .calc-box { background:rgba(0,229,255,.04); border:1px solid rgba(0,229,255,.1); border-radius:10px; padding:14px; text-align:center; }
        .calc-label { font-size:.68rem; color:rgba(200,230,255,.4); letter-spacing:2px; text-transform:uppercase; margin-bottom:8px; }
        .calc-val { font-family:'Orbitron',monospace; font-size:1.15rem; }
        .calc-unit { font-size:.68rem; color:rgba(200,230,255,.35); margin-top:4px; }

        /* CHARTS */
        .chart-section-title { font-family:'Orbitron',monospace; font-size:.78rem; letter-spacing:3px; text-transform:uppercase; margin:24px 0 14px; padding:10px 16px; border-radius:8px; display:inline-block; }
        .chart-wrap { background:var(--bg-panel); border:1px solid rgba(0,229,255,.12); border-radius:16px; padding:20px 22px; margin-bottom:16px; backdrop-filter:blur(10px); }
        .chart-title { font-family:'Orbitron',monospace; font-size:.75rem; letter-spacing:2px; text-transform:uppercase; margin-bottom:14px; font-weight:600; }
        .cI   .chart-title { color:var(--cyan); }
        .cU1  .chart-title { color:var(--yellow); }
        .cU2  .chart-title { color:var(--purple); }
        .cR1  .chart-title { color:var(--orange); }
        .cR2  .chart-title { color:var(--red); }
        .cQ1  .chart-title { color:var(--green); }
        .cQ2  .chart-title { color:var(--teal); }
        canvas { max-height:150px !important; }

        /* CHATBOT */
        .chat-layout { display:grid; grid-template-columns:1fr 260px; gap:20px; height:calc(100vh - 160px); }
        .chat-main { display:flex; flex-direction:column; background:var(--bg-panel); border:1px solid rgba(0,229,255,.15); border-radius:16px; overflow:hidden; backdrop-filter:blur(12px); }
        .chat-header { padding:16px 22px; border-bottom:1px solid rgba(0,229,255,.12); background:rgba(0,10,30,.6); display:flex; align-items:center; gap:12px; }
        .chat-header .bot-avatar { width:36px;height:36px; border-radius:50%; background:linear-gradient(135deg,rgba(0,229,255,.2),rgba(0,255,157,.1)); border:1px solid rgba(0,229,255,.3); display:flex;align-items:center;justify-content:center; font-size:1.1rem; }
        .chat-header .bot-name { font-family:'Orbitron',monospace; font-size:.8rem; color:var(--cyan); font-weight:700; letter-spacing:1px; }
        .chat-header .bot-status { font-size:.68rem; color:var(--green); letter-spacing:1px; }
        #chatBox { flex:1; overflow-y:auto; padding:20px; display:flex; flex-direction:column; gap:14px; }
        #chatBox::-webkit-scrollbar{width:4px} #chatBox::-webkit-scrollbar-track{background:transparent} #chatBox::-webkit-scrollbar-thumb{background:rgba(0,229,255,.2);border-radius:2px}
        .msg-row { display:flex; align-items:flex-end; gap:10px; }
        .msg-row.user { flex-direction:row-reverse; }
        .msg-avatar { width:30px;height:30px; border-radius:50%; display:flex;align-items:center;justify-content:center; font-size:.85rem; flex-shrink:0; }
        .msg-avatar.bot { background:rgba(0,229,255,.1); border:1px solid rgba(0,229,255,.2); }
        .msg-avatar.user-av { background:rgba(255,230,0,.1); border:1px solid rgba(255,230,0,.2); }
        .bubble { max-width:72%; padding:12px 16px; border-radius:14px; font-size:.88rem; line-height:1.6; }
        .bubble.bot-b { background:rgba(0,229,255,.07); border:1px solid rgba(0,229,255,.15); color:rgba(200,230,255,.9); border-bottom-left-radius:4px; }
        .bubble.user-b { background:rgba(255,230,0,.08); border:1px solid rgba(255,230,0,.15); color:rgba(255,240,150,.9); border-bottom-right-radius:4px; }
        .typing-b { background:rgba(0,229,255,.06); border:1px solid rgba(0,229,255,.12); }
        .typing-dots { display:flex; gap:4px; align-items:center; height:20px; }
        .typing-dots span { width:6px;height:6px; border-radius:50%; background:var(--cyan); animation:typing 1.4s infinite; }
        .typing-dots span:nth-child(2){animation-delay:.2s} .typing-dots span:nth-child(3){animation-delay:.4s}
        @keyframes typing { 0%,60%,100%{opacity:.2;transform:scale(.8)} 30%{opacity:1;transform:scale(1.1)} }
        .chat-input-area { padding:16px 20px; border-top:1px solid rgba(0,229,255,.1); display:flex; gap:10px; background:rgba(0,10,30,.5); }
        #userInput { flex:1; background:rgba(0,10,30,.8); border:1px solid rgba(0,229,255,.2); border-radius:10px; padding:11px 16px; color:#c8e6ff; font-family:'Rajdhani',sans-serif; font-size:.92rem; outline:none; transition:border-color .2s; }
        #userInput:focus{border-color:rgba(0,229,255,.5)} #userInput::placeholder{color:rgba(200,230,255,.3)}
        .send-btn { background:linear-gradient(135deg,rgba(0,229,255,.15),rgba(0,229,255,.05)); border:1px solid rgba(0,229,255,.3); border-radius:10px; padding:11px 18px; color:var(--cyan); cursor:pointer; font-size:1rem; transition:all .2s; }
        .send-btn:hover{background:rgba(0,229,255,.2);border-color:var(--cyan)}
        .chat-sidebar { display:flex; flex-direction:column; gap:14px; }
        .quick-panel { background:var(--bg-panel); border:1px solid rgba(0,229,255,.12); border-radius:14px; padding:18px; backdrop-filter:blur(10px); }
        .quick-panel h4 { font-family:'Orbitron',monospace; font-size:.7rem; color:var(--cyan); letter-spacing:2px; text-transform:uppercase; margin-bottom:12px; }
        .quick-btn { width:100%; text-align:left; background:rgba(0,229,255,.04); border:1px solid rgba(0,229,255,.12); border-radius:8px; padding:10px 12px; color:rgba(200,230,255,.7); font-size:.8rem; cursor:pointer; margin-bottom:7px; transition:all .2s; font-family:'Rajdhani',sans-serif; letter-spacing:.5px; }
        .quick-btn:hover{background:rgba(0,229,255,.1);color:var(--cyan);border-color:rgba(0,229,255,.3)}
        .context-panel { background:var(--bg-panel); border:1px solid rgba(0,255,157,.15); border-radius:14px; padding:18px; }
        .context-panel h4 { font-family:'Orbitron',monospace; font-size:.7rem; color:var(--green); letter-spacing:2px; text-transform:uppercase; margin-bottom:12px; }
        .ctx-row { display:flex; justify-content:space-between; align-items:center; padding:7px 0; border-bottom:1px solid rgba(0,229,255,.07); font-size:.78rem; }
        .ctx-row:last-child{border-bottom:none}
        .ctx-label{color:rgba(200,230,255,.45)}
        .ctx-val{font-family:'Orbitron',monospace;font-size:.72rem;color:var(--cyan)}

        @media(max-width:900px){
            .metric-cards{grid-template-columns:1fr}
            .calc-grid{grid-template-columns:repeat(2,1fr)}
            .chat-layout{grid-template-columns:1fr;height:auto}
            #main{padding:16px}
        }
    </style>
</head>
<body>

<!-- SIDEBAR -->
<nav id="sidebar">
    <div class="sidebar-logo">
        <span class="logo-icon">⚡</span>
        <h2>ESP32-S3<br>Điện Học</h2>
        <p>REALTIME MONITOR</p>
    </div>
    <div class="sidebar-nav">
        <div class="nav-label">Menu</div>
        <a class="nav-item active" onclick="switchPage('home',this);return false;" href="#">
            <span class="nav-icon">🏠</span> Trang Chủ
        </a>
        <a class="nav-item" onclick="switchPage('charts',this);return false;" href="#">
            <span class="nav-icon">📈</span> Biểu Đồ
        </a>
        <a class="nav-item" onclick="switchPage('chat',this);return false;" href="#">
            <span class="nav-icon">🤖</span> Chatbot AI
        </a>
    </div>
    <div class="sidebar-footer">ESP32-S3 · Flask · Cloudflare</div>
</nav>

<!-- MAIN -->
<main id="main">

    <!-- TRANG CHỦ -->
    <div class="page active" id="page-home">
        <div class="page-header">
            <h1>⚡ Giám Sát Thời Gian Thực</h1>
            <p>1 cảm biến dòng · 2 cảm biến điện áp · Cập nhật mỗi 1 giây</p>
        </div>

        <div class="status-bar">
            <div class="status-dot" id="statusDot"></div>
            <span class="status-text" id="statusText">Đang chờ dữ liệu...</span>
            <span class="status-time" id="statusTime">--:--:--</span>
        </div>

        <!-- 3 Metric Cards -->
        <div class="metric-cards">
            <div class="metric-card card-I">
                <div class="glow-bg"></div>
                <div class="metric-label">⚡ Dòng Điện</div>
                <div class="metric-name">Cường độ dòng điện I</div>
                <div class="metric-value" id="valI">—</div>
                <div class="metric-unit">AMPERE (A)</div>
            </div>
            <div class="metric-card card-U1">
                <div class="glow-bg"></div>
                <div class="metric-label">🔋 Điện Áp 1</div>
                <div class="metric-name">Hiệu điện thế U₁</div>
                <div class="metric-value" id="valU1">—</div>
                <div class="metric-unit">VOLT (V)</div>
            </div>
            <div class="metric-card card-U2">
                <div class="glow-bg"></div>
                <div class="metric-label">🔋 Điện Áp 2</div>
                <div class="metric-name">Hiệu điện thế U₂</div>
                <div class="metric-value" id="valU2">—</div>
                <div class="metric-unit">VOLT (V)</div>
            </div>
        </div>

        <!-- Thông số tính toán -->
        <div class="panel">
            <div style="font-family:'Orbitron',monospace;font-size:.75rem;color:var(--cyan);letter-spacing:2px;text-transform:uppercase;margin-bottom:18px;">
                📊 Thông Số Tính Toán
            </div>
            <div class="calc-grid">
                <div class="calc-box">
                    <div class="calc-label">Công suất P₁ = U₁×I</div>
                    <div class="calc-val" style="color:var(--pink);" id="calcP1">—</div>
                    <div class="calc-unit">Watt (W)</div>
                </div>
                <div class="calc-box">
                    <div class="calc-label">Điện trở R₁ = U₁/I</div>
                    <div class="calc-val" style="color:var(--orange);" id="calcR1">—</div>
                    <div class="calc-unit">Ohm (Ω)</div>
                </div>
                <div class="calc-box">
                    <div class="calc-label">Nhiệt lượng Q₁ = P₁×t</div>
                    <div class="calc-val" style="color:var(--green);" id="calcQ1">—</div>
                    <div class="calc-unit">Joule (J)</div>
                </div>
                <div class="calc-box">
                    <div class="calc-label">Công suất P₂ = U₂×I</div>
                    <div class="calc-val" style="color:var(--pink);" id="calcP2">—</div>
                    <div class="calc-unit">Watt (W)</div>
                </div>
                <div class="calc-box">
                    <div class="calc-label">Điện trở R₂ = U₂/I</div>
                    <div class="calc-val" style="color:var(--red);" id="calcR2">—</div>
                    <div class="calc-unit">Ohm (Ω)</div>
                </div>
                <div class="calc-box">
                    <div class="calc-label">Nhiệt lượng Q₂ = P₂×t</div>
                    <div class="calc-val" style="color:var(--teal);" id="calcQ2">—</div>
                    <div class="calc-unit">Joule (J)</div>
                </div>
            </div>
        </div>

        <!-- Số mẫu + V drift -->
        <div class="panel" style="display:grid;grid-template-columns:1fr 1fr;gap:16px;padding:16px;">
            <div style="text-align:center;">
                <div style="font-size:.68rem;color:rgba(200,230,255,.4);letter-spacing:2px;text-transform:uppercase;margin-bottom:8px;">Số điểm đã nhận</div>
                <div style="font-family:'Orbitron',monospace;font-size:1.6rem;color:var(--green);" id="calcCount">0</div>
                <div style="font-size:.68rem;color:rgba(200,230,255,.35);margin-top:4px;">Samples</div>
            </div>
            <div style="text-align:center;">
                <div style="font-size:.68rem;color:rgba(200,230,255,.4);letter-spacing:2px;text-transform:uppercase;margin-bottom:8px;">Vận tốc drift V</div>
                <div style="font-family:'Orbitron',monospace;font-size:1.1rem;color:var(--cyan);" id="calcV">—</div>
                <div style="font-size:.68rem;color:rgba(200,230,255,.35);margin-top:4px;">× 10⁻⁵ m/s</div>
            </div>
        </div>
    </div>

    <!-- BIỂU ĐỒ -->
    <div class="page" id="page-charts">
        <div class="page-header">
            <h1>📈 Biểu Đồ Dữ Liệu</h1>
            <p>7 biểu đồ · Lịch sử tối đa 60 điểm gần nhất</p>
        </div>

        <div style="font-family:'Orbitron',monospace;font-size:.72rem;color:var(--cyan);letter-spacing:3px;text-transform:uppercase;margin-bottom:12px;padding:8px 14px;background:rgba(0,229,255,.06);border:1px solid rgba(0,229,255,.15);border-radius:8px;display:inline-block;">
            📡 Đầu Vào Cảm Biến
        </div>
        <div class="chart-wrap cI">
            <div class="chart-title">⚡ Cường Độ Dòng Điện I (A)</div>
            <canvas id="chartI"></canvas>
        </div>
        <div class="chart-wrap cU1">
            <div class="chart-title">🔋 Hiệu Điện Thế U₁ (V)</div>
            <canvas id="chartU1"></canvas>
        </div>
        <div class="chart-wrap cU2">
            <div class="chart-title">🔋 Hiệu Điện Thế U₂ (V)</div>
            <canvas id="chartU2"></canvas>
        </div>

        <div style="font-family:'Orbitron',monospace;font-size:.72rem;color:var(--orange);letter-spacing:3px;text-transform:uppercase;margin:24px 0 12px;padding:8px 14px;background:rgba(255,140,0,.06);border:1px solid rgba(255,140,0,.2);border-radius:8px;display:inline-block;">
            📐 Điện Trở
        </div>
        <div class="chart-wrap cR1">
            <div class="chart-title">📐 Điện Trở R₁ = U₁/I (Ω)</div>
            <canvas id="chartR1"></canvas>
        </div>
        <div class="chart-wrap cR2">
            <div class="chart-title">📐 Điện Trở R₂ = U₂/I (Ω)</div>
            <canvas id="chartR2"></canvas>
        </div>

        <div style="font-family:'Orbitron',monospace;font-size:.72rem;color:var(--green);letter-spacing:3px;text-transform:uppercase;margin:24px 0 12px;padding:8px 14px;background:rgba(0,255,157,.06);border:1px solid rgba(0,255,157,.2);border-radius:8px;display:inline-block;">
            🌡️ Nhiệt Lượng Tích Lũy
        </div>
        <div class="chart-wrap cQ1">
            <div class="chart-title">🌡️ Nhiệt Lượng Q₁ = P₁×t (J)</div>
            <canvas id="chartQ1"></canvas>
        </div>
        <div class="chart-wrap cQ2">
            <div class="chart-title">🌡️ Nhiệt Lượng Q₂ = P₂×t (J)</div>
            <canvas id="chartQ2"></canvas>
        </div>
    </div>

    <!-- CHATBOT -->
    <div class="page" id="page-chat">
        <div class="page-header">
            <h1>🤖 Chatbot Điện Học</h1>
            <p>Hỏi về I, U, P, R, Q và phân tích số liệu thời gian thực</p>
        </div>
        <div class="chat-layout">
            <div class="chat-main">
                <div class="chat-header">
                    <div class="bot-avatar">🤖</div>
                    <div>
                        <div class="bot-name">AI Điện Học</div>
                        <div class="bot-status">● Online</div>
                    </div>
                </div>
                <div id="chatBox">
                    <div class="msg-row">
                        <div class="msg-avatar bot">🤖</div>
                        <div class="bubble bot-b">
                            Xin chào! Hệ thống có 1 cảm biến dòng (I) và 2 cảm biến điện áp (U₁, U₂). Tôi có thể giúp bạn hiểu về P, R, Q hoặc phân tích số liệu đang đo nhé! ⚡
                        </div>
                    </div>
                </div>
                <div class="chat-input-area">
                    <input type="text" id="userInput" placeholder="Hỏi về điện học..." />
                    <button class="send-btn" onclick="sendMessage()">➤</button>
                </div>
            </div>
            <div class="chat-sidebar">
                <div class="quick-panel">
                    <h4>💬 Câu Hỏi Nhanh</h4>
                    <button class="quick-btn" onclick="quickAsk('Cường độ dòng điện là gì?')">⚡ Cường độ dòng điện?</button>
                    <button class="quick-btn" onclick="quickAsk('Công thức tính công suất điện?')">⚡ Công suất P?</button>
                    <button class="quick-btn" onclick="quickAsk('Điện trở R là gì? Đơn vị là gì?')">📐 Điện trở R?</button>
                    <button class="quick-btn" onclick="quickAsk('Nhiệt lượng Q tỏa ra là gì? Công thức?')">🌡️ Nhiệt lượng Q?</button>
                    <button class="quick-btn" onclick="quickAskWithData()">📊 Phân tích số liệu hiện tại</button>
                    <button class="quick-btn" onclick="quickAsk('Định luật Ohm là gì?')">📐 Định luật Ohm</button>
                </div>
                <div class="context-panel">
                    <h4>📡 Giá Trị Hiện Tại</h4>
                    <div class="ctx-row"><span class="ctx-label">I (A)</span><span class="ctx-val" id="ctxI">—</span></div>
                    <div class="ctx-row"><span class="ctx-label">U₁ (V)</span><span class="ctx-val" id="ctxU1">—</span></div>
                    <div class="ctx-row"><span class="ctx-label">U₂ (V)</span><span class="ctx-val" id="ctxU2">—</span></div>
                    <div class="ctx-row"><span class="ctx-label">R₁ (Ω)</span><span class="ctx-val" id="ctxR1">—</span></div>
                    <div class="ctx-row"><span class="ctx-label">R₂ (Ω)</span><span class="ctx-val" id="ctxR2">—</span></div>
                    <div class="ctx-row"><span class="ctx-label">Q₁ (J)</span><span class="ctx-val" id="ctxQ1">—</span></div>
                    <div class="ctx-row"><span class="ctx-label">Q₂ (J)</span><span class="ctx-val" id="ctxQ2">—</span></div>
                </div>
            </div>
        </div>
    </div>

</main>

<script>
// NAVIGATION
function switchPage(name, el) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.getElementById('page-' + name).classList.add('active');
    el.classList.add('active');
    return false;
}

// CHARTS
function makeChart(id, label, color, fill=true) {
    const ctx = document.getElementById(id).getContext('2d');
    return new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: label,
                data: [],
                borderColor: color,
                backgroundColor: fill ? color + '18' : 'transparent',
                borderWidth: 2,
                pointRadius: 2,
                pointBackgroundColor: color,
                tension: 0.4,
                fill: fill,
            }]
        },
        options: {
            responsive: true,
            animation: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { ticks: { color: 'rgba(200,230,255,0.4)', font: { size: 10 }, maxTicksLimit: 10 }, grid: { color: 'rgba(255,255,255,0.04)' } },
                y: { ticks: { color: 'rgba(200,230,255,0.4)', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.06)' } }
            }
        }
    });
}

const chartI  = makeChart('chartI',  'I (A)',  '#00e5ff');
const chartU1 = makeChart('chartU1', 'U₁ (V)', '#ffe600');
const chartU2 = makeChart('chartU2', 'U₂ (V)', '#bf5fff');
const chartR1 = makeChart('chartR1', 'R₁ (Ω)', '#ff8c00');
const chartR2 = makeChart('chartR2', 'R₂ (Ω)', '#ff4f4f');
const chartQ1 = makeChart('chartQ1', 'Q₁ (J)', '#00ff9d');
const chartQ2 = makeChart('chartQ2', 'Q₂ (J)', '#00ffc8');

function setChart(chart, labels, values) {
    chart.data.labels = labels;
    chart.data.datasets[0].data = values;
    chart.update('none');
}

// FETCH
let lastI=0, lastU1=0, lastU2=0, lastR1=0, lastR2=0, lastQ1=0, lastQ2=0;

async function fetchData() {
    try {
        const res = await fetch('/api/latest');
        const d = await res.json();

        lastI  = d.I;  lastU1 = d.U1; lastU2 = d.U2;
        lastR1 = d.R1; lastR2 = d.R2;
        lastQ1 = d.Q1; lastQ2 = d.Q2;

        const P1 = lastI * lastU1;
        const P2 = lastI * lastU2;

        // Cards
        document.getElementById('valI').textContent  = lastI.toFixed(4);
        document.getElementById('valU1').textContent = lastU1.toFixed(4);
        document.getElementById('valU2').textContent = lastU2.toFixed(4);

        // Calc
        document.getElementById('calcP1').textContent = P1.toFixed(4);
        document.getElementById('calcR1').textContent = lastR1.toFixed(4);
        document.getElementById('calcQ1').textContent = lastQ1.toFixed(3);
        document.getElementById('calcP2').textContent = P2.toFixed(4);
        document.getElementById('calcR2').textContent = lastR2.toFixed(4);
        document.getElementById('calcQ2').textContent = lastQ2.toFixed(3);
        document.getElementById('calcCount').textContent = d.count || 0;
        document.getElementById('calcV').textContent = d.V ? (d.V / 1e-5).toFixed(4) : '—';

        // Status
        const dot = document.getElementById('statusDot');
        if (d.timestamp) {
            dot.classList.remove('offline');
            document.getElementById('statusText').textContent = 'ESP32-S3 đang gửi dữ liệu · Kết nối tốt';
            document.getElementById('statusTime').textContent  = d.timestamp;
        } else {
            dot.classList.add('offline');
            document.getElementById('statusText').textContent = 'Chưa nhận được dữ liệu từ ESP32-S3';
        }

        // Chatbot context
        document.getElementById('ctxI').textContent  = lastI.toFixed(4);
        document.getElementById('ctxU1').textContent = lastU1.toFixed(4);
        document.getElementById('ctxU2').textContent = lastU2.toFixed(4);
        document.getElementById('ctxR1').textContent = lastR1.toFixed(4);
        document.getElementById('ctxR2').textContent = lastR2.toFixed(4);
        document.getElementById('ctxQ1').textContent = lastQ1.toFixed(3);
        document.getElementById('ctxQ2').textContent = lastQ2.toFixed(3);

        // Charts
        const ts = d.timestamps;
        setChart(chartI,  ts, d.histI);
        setChart(chartU1, ts, d.histU1);
        setChart(chartU2, ts, d.histU2);
        setChart(chartR1, ts, d.histR1);
        setChart(chartR2, ts, d.histR2);
        setChart(chartQ1, ts, d.histQ1);
        setChart(chartQ2, ts, d.histQ2);

    } catch(e) {
        document.getElementById('statusDot').classList.add('offline');
        document.getElementById('statusText').textContent = 'Lỗi kết nối server';
    }
}

fetchData();
setInterval(fetchData, 1000);

// CHATBOT
function addMessage(text, isUser) {
    const chatBox = document.getElementById('chatBox');
    const row = document.createElement('div');
    row.className = 'msg-row' + (isUser ? ' user' : '');
    const avatar = document.createElement('div');
    avatar.className = 'msg-avatar ' + (isUser ? 'user-av' : 'bot');
    avatar.textContent = isUser ? '👤' : '🤖';
    const bubble = document.createElement('div');
    bubble.className = 'bubble ' + (isUser ? 'user-b' : 'bot-b');
    bubble.textContent = text;
    row.appendChild(avatar); row.appendChild(bubble);
    chatBox.appendChild(row);
    chatBox.scrollTop = chatBox.scrollHeight;
}
function showTyping() {
    const chatBox = document.getElementById('chatBox');
    const row = document.createElement('div');
    row.className='msg-row'; row.id='typingIndicator';
    const av = document.createElement('div'); av.className='msg-avatar bot'; av.textContent='🤖';
    const b  = document.createElement('div'); b.className='bubble typing-b';
    b.innerHTML='<div class="typing-dots"><span></span><span></span><span></span></div>';
    row.appendChild(av); row.appendChild(b);
    chatBox.appendChild(row); chatBox.scrollTop=chatBox.scrollHeight;
}
function removeTyping() { const el=document.getElementById('typingIndicator'); if(el) el.remove(); }

async function sendMessage() {
    const input = document.getElementById('userInput');
    const message = input.value.trim();
    if (!message) return;
    addMessage(message, true); input.value=''; showTyping();
    try {
        const res = await fetch('/chat', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({message}) });
        const data = await res.json();
        removeTyping(); addMessage(data.response, false);
    } catch(e) { removeTyping(); addMessage('Lỗi kết nối chatbot. Thử lại sau nhé!', false); }
}
function quickAsk(text) { document.getElementById('userInput').value=text; sendMessage(); }
function quickAskWithData() {
    const P1=(lastI*lastU1).toFixed(4), P2=(lastI*lastU2).toFixed(4);
    const msg = `Số liệu đo được: I=${lastI.toFixed(4)}A, U₁=${lastU1.toFixed(4)}V, U₂=${lastU2.toFixed(4)}V. Tính toán: P₁=${P1}W, R₁=${lastR1.toFixed(4)}Ω, Q₁=${lastQ1.toFixed(3)}J | P₂=${P2}W, R₂=${lastR2.toFixed(4)}Ω, Q₂=${lastQ2.toFixed(3)}J. Bạn hãy phân tích các giá trị này giúp tôi?`;
    document.getElementById('userInput').value=msg; sendMessage();
}
document.getElementById('userInput').addEventListener('keypress', e => { if(e.key==='Enter') sendMessage(); });
</script>
</body>
</html>
'''

# ================== ROUTES ==================

@app.route('/')
def index():
    return render_template_string(HTML)


@app.route('/data', methods=['POST'])
def receive_data():
    """ESP32-S3 POST dữ liệu lên đây.
    JSON: {"I": 0.1, "U1": 3.3, "U2": 5.0, "V": 1.5e-5}
    """
    global Q1_total, Q2_total, last_recv_time
    try:
        d = request.get_json(force=True)
        I  = float(d.get('I',  0))
        U1 = float(d.get('U1', 0))
        U2 = float(d.get('U2', 0))
        V  = float(d.get('V',  0))
        ts = time.strftime('%H:%M:%S')

        # dt để tính Q
        now = time.time()
        dt = (now - last_recv_time) if last_recv_time else 1.0
        last_recv_time = now

        P1 = I * U1
        P2 = I * U2
        R1 = (U1 / I) if I != 0 else 0
        R2 = (U2 / I) if I != 0 else 0
        Q1_total += P1 * dt
        Q2_total += P2 * dt

        with data_lock:
            latest_data.update({'I': I, 'U1': U1, 'U2': U2, 'V': V, 'timestamp': ts})

            history_data['I'].append(I)
            history_data['U1'].append(U1)
            history_data['U2'].append(U2)
            history_data['R1'].append(round(R1, 4))
            history_data['R2'].append(round(R2, 4))
            history_data['Q1'].append(round(Q1_total, 4))
            history_data['Q2'].append(round(Q2_total, 4))
            history_data['timestamps'].append(ts)

            for key in history_data:
                if len(history_data[key]) > MAX_HISTORY:
                    history_data[key] = history_data[key][-MAX_HISTORY:]

        print(f"✅ [{ts}] I={I:.4f}A U1={U1:.2f}V U2={U2:.2f}V | R1={R1:.2f}Ω R2={R2:.2f}Ω | Q1={Q1_total:.2f}J Q2={Q2_total:.2f}J")
        return jsonify({"status": "ok"})
    except Exception as ex:
        print(f"❌ Lỗi: {ex}")
        return jsonify({"status": "error", "msg": str(ex)}), 400


@app.route('/api/latest')
def api_latest():
    with data_lock:
        return jsonify({
            "I":    latest_data['I'],
            "U1":   latest_data['U1'],
            "U2":   latest_data['U2'],
            "V":    latest_data['V'],
            "R1":   history_data['R1'][-1] if history_data['R1'] else 0,
            "R2":   history_data['R2'][-1] if history_data['R2'] else 0,
            "Q1":   Q1_total,
            "Q2":   Q2_total,
            "timestamp": latest_data['timestamp'],
            "histI":   history_data['I'][-60:],
            "histU1":  history_data['U1'][-60:],
            "histU2":  history_data['U2'][-60:],
            "histR1":  history_data['R1'][-60:],
            "histR2":  history_data['R2'][-60:],
            "histQ1":  history_data['Q1'][-60:],
            "histQ2":  history_data['Q2'][-60:],
            "timestamps": history_data['timestamps'][-60:],
            "count": len(history_data['I'])
        })


@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    user_message = data.get('message', '')
    if not user_message:
        return jsonify({"response": "Bạn muốn hỏi gì về điện học?"})
    try:
        response = chat_session.send_message(user_message)
        return jsonify({"response": response.text})
    except Exception as ex:
        print(f"Lỗi Gemini: {ex}")
        return jsonify({"response": "Xin lỗi, chatbot đang bận. Kiểm tra lại API key nhé!"})


if __name__ == '__main__':
    print("⚡ Server Đo Điện ESP32-S3 đang chạy...")
    print("🌐 http://127.0.0.1:5000")
    print('📡 JSON: {"I":0.1,"U1":3.3,"U2":5.0,"V":1.5e-5}')
    app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)