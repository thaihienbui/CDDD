from flask import Flask, render_template_string, request, jsonify
import time
import threading
import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()

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
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
    <meta http-equiv="Content-Security-Policy" content="upgrade-insecure-requests">
    <title>⚡ Đo Điện ESP32-S3</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Rajdhani:wght@400;500;600&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        /* ===== VARIABLES ===== */
        :root {
            --cyan:    #00e5ff;
            --green:   #00ff9d;
            --pink:    #ff2d78;
            --yellow:  #ffe600;
            --orange:  #ff8c00;
            --purple:  #bf5fff;
            --teal:    #00ffc8;
            --red:     #ff4f4f;
            --bg-dark: #030a1a;
            --bg-panel:rgba(5,15,40,0.92);
            --sidebar-w: 220px;
            --nav-h: 64px; /* mobile bottom nav height */
        }

        /* ===== RESET ===== */
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            background-color: var(--bg-dark);
            background-image:
                radial-gradient(ellipse at 20% 50%, rgba(0,60,120,0.4) 0%, transparent 60%),
                radial-gradient(ellipse at 80% 20%, rgba(0,80,60,0.25) 0%, transparent 50%),
                radial-gradient(ellipse at 60% 80%, rgba(80,0,80,0.2) 0%, transparent 50%);
            color: #c8e6ff;
            font-family: 'Rajdhani', sans-serif;
            min-height: 100vh;
            min-height: 100dvh;
            overflow-x: hidden;
        }

        /* ===== SIDEBAR (tablet+) ===== */
        #sidebar {
            width: var(--sidebar-w);
            min-height: 100vh;
            background: linear-gradient(180deg, rgba(0,10,30,.98), rgba(0,20,50,.95));
            border-right: 1px solid rgba(0,229,255,.2);
            display: flex;
            flex-direction: column;
            position: fixed;
            top: 0; left: 0;
            z-index: 200;
            box-shadow: 4px 0 30px rgba(0,229,255,.1);
            transition: transform .3s cubic-bezier(.4,0,.2,1);
        }
        .sidebar-logo {
            padding: 24px 20px 20px;
            border-bottom: 1px solid rgba(0,229,255,.15);
            text-align: center;
        }
        .sidebar-logo .logo-icon {
            font-size: 2.2rem;
            display: block;
            margin-bottom: 6px;
            filter: drop-shadow(0 0 12px var(--yellow));
            animation: pulse 2s ease-in-out infinite;
        }
        @keyframes pulse {
            0%,100% { transform:scale(1);   filter:drop-shadow(0 0 12px var(--yellow)); }
            50%      { transform:scale(1.1); filter:drop-shadow(0 0 22px var(--yellow)); }
        }
        .sidebar-logo h2 {
            font-family: 'Orbitron', monospace;
            font-size: .7rem; font-weight: 700;
            color: var(--cyan); letter-spacing: 2px;
            text-transform: uppercase; line-height: 1.5;
        }
        .sidebar-logo p { font-size:.65rem; color:rgba(200,230,255,.4); margin-top:4px; letter-spacing:1px; }
        .sidebar-nav { flex:1; padding:16px 0; overflow-y:auto; }
        .nav-label {
            font-size:.58rem; letter-spacing:3px; text-transform:uppercase;
            color:rgba(200,230,255,.3); padding:0 20px 8px; margin-top:8px;
        }
        .nav-item {
            display:flex; align-items:center; gap:12px;
            padding:13px 20px; cursor:pointer; transition:all .2s;
            border-left:3px solid transparent;
            color:rgba(200,230,255,.6); font-size:.93rem;
            font-weight:500; letter-spacing:.5px; text-decoration:none;
        }
        .nav-item:hover  { background:rgba(0,229,255,.06); color:var(--cyan); border-left-color:rgba(0,229,255,.4); }
        .nav-item.active { background:rgba(0,229,255,.1);  color:var(--cyan); border-left-color:var(--cyan); }
        .nav-item .nav-icon { font-size:1.1rem; width:22px; text-align:center; }
        .sidebar-footer {
            padding:14px 20px;
            border-top:1px solid rgba(0,229,255,.1);
            font-size:.62rem; color:rgba(200,230,255,.3);
            text-align:center; letter-spacing:1px;
        }

        /* ===== MOBILE BOTTOM NAV ===== */
        #bottom-nav {
            display: none;
            position: fixed;
            bottom: 0; left: 0; right: 0;
            height: var(--nav-h);
            background: rgba(3,10,26,.97);
            border-top: 1px solid rgba(0,229,255,.18);
            z-index: 200;
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
        }
        .bottom-nav-inner {
            display: flex;
            height: 100%;
        }
        .bnav-item {
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 3px;
            cursor: pointer;
            transition: all .2s;
            border-top: 2px solid transparent;
            color: rgba(200,230,255,.45);
            font-size: .6rem;
            font-family: 'Rajdhani', sans-serif;
            letter-spacing: .5px;
            font-weight: 600;
            text-transform: uppercase;
            user-select: none;
            -webkit-tap-highlight-color: transparent;
        }
        .bnav-item .bni { font-size: 1.3rem; line-height: 1; }
        .bnav-item.active {
            color: var(--cyan);
            border-top-color: var(--cyan);
            background: rgba(0,229,255,.06);
        }

        /* ===== MAIN CONTENT ===== */
        #main {
            margin-left: var(--sidebar-w);
            padding: 28px;
            min-height: 100vh;
        }
        .page { display: none; }
        .page.active { display: block; }

        /* ===== PAGE HEADER ===== */
        .page-header {
            margin-bottom: 24px;
            padding-bottom: 16px;
            border-bottom: 1px solid rgba(0,229,255,.15);
        }
        .page-header h1 {
            font-family: 'Orbitron', monospace;
            font-size: 1.2rem; font-weight: 700;
            color: var(--cyan); letter-spacing: 3px;
            text-transform: uppercase; margin-bottom: 4px;
            text-shadow: 0 0 20px rgba(0,229,255,.5);
        }
        .page-header p { font-size:.82rem; color:rgba(200,230,255,.45); letter-spacing:1px; }

        /* ===== PANEL ===== */
        .panel {
            background: var(--bg-panel);
            border: 1px solid rgba(0,229,255,.15);
            border-radius: 16px;
            padding: 20px;
            backdrop-filter: blur(12px);
            box-shadow: 0 8px 32px rgba(0,0,0,.4), inset 0 1px 0 rgba(255,255,255,.05);
            margin-bottom: 18px;
        }
        .panel-title {
            font-family: 'Orbitron', monospace;
            font-size: .72rem; color: var(--cyan);
            letter-spacing: 2px; text-transform: uppercase;
            margin-bottom: 16px; font-weight: 600;
        }

        /* ===== STATUS BAR ===== */
        .status-bar {
            display: flex; align-items: center; gap: 14px;
            padding: 12px 18px;
            background: rgba(0,229,255,.04);
            border: 1px solid rgba(0,229,255,.12);
            border-radius: 12px;
            margin-bottom: 18px;
            flex-wrap: wrap;
            gap: 10px;
        }
        .status-dot {
            width: 8px; height: 8px; border-radius: 50%;
            background: var(--green); box-shadow: 0 0 8px var(--green);
            animation: blink 1.5s ease-in-out infinite;
            flex-shrink: 0;
        }
        .status-dot.offline { background:#ff4444; box-shadow:0 0 8px #ff4444; animation:none; }
        @keyframes blink { 0%,100%{opacity:1} 50%{opacity:.3} }
        .status-text { font-size:.8rem; color:rgba(200,230,255,.6); letter-spacing:1px; }
        .status-time {
            font-family: 'Orbitron', monospace;
            font-size: .7rem; color: rgba(200,230,255,.35);
            margin-left: auto;
        }

        /* ===== METRIC CARDS ===== */
        .metric-cards {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 14px;
            margin-bottom: 18px;
        }
        .metric-card {
            background: var(--bg-panel);
            border-radius: 16px;
            padding: 18px 16px;
            border: 1px solid rgba(0,229,255,.15);
            position: relative; overflow: hidden;
            backdrop-filter: blur(10px);
            transition: transform .2s, box-shadow .2s;
        }
        .metric-card:hover { transform:translateY(-3px); box-shadow:0 14px 36px rgba(0,0,0,.5); }
        .metric-card::before {
            content: ''; position: absolute;
            top: 0; left: 0; right: 0; height: 3px;
        }
        .card-I::before  { background:linear-gradient(90deg,var(--cyan),transparent); }
        .card-U1::before { background:linear-gradient(90deg,var(--yellow),transparent); }
        .card-U2::before { background:linear-gradient(90deg,var(--purple),transparent); }
        .metric-card .glow-bg {
            position: absolute;
            width: 100px; height: 100px; border-radius: 50%;
            opacity: .07; top: -18px; right: -18px;
        }
        .card-I  .glow-bg { background:var(--cyan); }
        .card-U1 .glow-bg { background:var(--yellow); }
        .card-U2 .glow-bg { background:var(--purple); }
        .metric-label {
            font-size: .65rem; letter-spacing: 2.5px;
            text-transform: uppercase; margin-bottom: 6px; font-weight: 600;
        }
        .card-I  .metric-label { color:var(--cyan); }
        .card-U1 .metric-label { color:var(--yellow); }
        .card-U2 .metric-label { color:var(--purple); }
        .metric-name { font-size:.68rem; color:rgba(200,230,255,.4); margin-bottom:10px; letter-spacing:1px; }
        .metric-value {
            font-family: 'Orbitron', monospace;
            font-size: 1.7rem; font-weight: 700;
            line-height: 1; margin-bottom: 5px;
        }
        .card-I  .metric-value { color:var(--cyan);   text-shadow:0 0 18px rgba(0,229,255,.6); }
        .card-U1 .metric-value { color:var(--yellow); text-shadow:0 0 18px rgba(255,230,0,.6); }
        .card-U2 .metric-value { color:var(--purple); text-shadow:0 0 18px rgba(191,95,255,.6); }
        .metric-unit { font-size:.65rem; color:rgba(200,230,255,.4); letter-spacing:2px; }

        /* ===== CALC GRID ===== */
        .calc-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
        }
        .calc-box {
            background: rgba(0,229,255,.04);
            border: 1px solid rgba(0,229,255,.1);
            border-radius: 10px;
            padding: 13px 10px;
            text-align: center;
        }
        .calc-label { font-size:.62rem; color:rgba(200,230,255,.4); letter-spacing:1.5px; text-transform:uppercase; margin-bottom:7px; }
        .calc-val   { font-family:'Orbitron',monospace; font-size:1.05rem; }
        .calc-unit  { font-size:.62rem; color:rgba(200,230,255,.35); margin-top:3px; }

        /* ===== SAMPLE + DRIFT ===== */
        .stat-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 14px;
        }
        .stat-box { text-align: center; }
        .stat-label { font-size:.62rem; color:rgba(200,230,255,.4); letter-spacing:2px; text-transform:uppercase; margin-bottom:6px; }
        .stat-val   { font-family:'Orbitron',monospace; }
        .stat-unit  { font-size:.62rem; color:rgba(200,230,255,.35); margin-top:3px; }

        /* ===== CHARTS ===== */
        .chart-section-badge {
            font-family: 'Orbitron', monospace;
            font-size: .68rem; letter-spacing:3px; text-transform:uppercase;
            margin-bottom: 12px; padding: 8px 14px;
            border-radius: 8px; display: inline-block;
        }
        .chart-wrap {
            background: var(--bg-panel);
            border: 1px solid rgba(0,229,255,.12);
            border-radius: 14px;
            padding: 18px 18px 14px;
            margin-bottom: 14px;
            backdrop-filter: blur(10px);
        }
        .chart-title {
            font-family:'Orbitron',monospace;
            font-size:.72rem; letter-spacing:2px;
            text-transform:uppercase; margin-bottom:12px; font-weight:600;
        }
        .cI  .chart-title  { color:var(--cyan); }
        .cU1 .chart-title  { color:var(--yellow); }
        .cU2 .chart-title  { color:var(--purple); }
        .cR1 .chart-title  { color:var(--orange); }
        .cR2 .chart-title  { color:var(--red); }
        .cQ1 .chart-title  { color:var(--green); }
        .cQ2 .chart-title  { color:var(--teal); }
        canvas { max-height: 140px !important; }

        /* ===== CHATBOT ===== */
        .chat-layout {
            display: grid;
            grid-template-columns: 1fr 250px;
            gap: 18px;
            height: calc(100vh - 150px);
            min-height: 500px;
        }
        .chat-main {
            display: flex; flex-direction: column;
            background: var(--bg-panel);
            border: 1px solid rgba(0,229,255,.15);
            border-radius: 16px; overflow: hidden;
            backdrop-filter: blur(12px);
            min-height: 0;
        }
        .chat-header {
            padding: 14px 20px;
            border-bottom: 1px solid rgba(0,229,255,.12);
            background: rgba(0,10,30,.6);
            display: flex; align-items: center; gap: 12px;
            flex-shrink: 0;
        }
        .chat-header .bot-avatar {
            width:34px; height:34px; border-radius:50%;
            background:linear-gradient(135deg,rgba(0,229,255,.2),rgba(0,255,157,.1));
            border:1px solid rgba(0,229,255,.3);
            display:flex; align-items:center; justify-content:center;
            font-size:1rem; flex-shrink:0;
        }
        .chat-header .bot-name  { font-family:'Orbitron',monospace; font-size:.78rem; color:var(--cyan); font-weight:700; letter-spacing:1px; }
        .chat-header .bot-status{ font-size:.65rem; color:var(--green); letter-spacing:1px; }
        #chatBox {
            flex: 1; overflow-y: auto;
            padding: 18px; display: flex;
            flex-direction: column; gap: 12px;
            min-height: 0;
        }
        #chatBox::-webkit-scrollbar{width:4px}
        #chatBox::-webkit-scrollbar-track{background:transparent}
        #chatBox::-webkit-scrollbar-thumb{background:rgba(0,229,255,.2);border-radius:2px}
        .msg-row { display:flex; align-items:flex-end; gap:9px; }
        .msg-row.user { flex-direction:row-reverse; }
        .msg-avatar {
            width:28px; height:28px; border-radius:50%;
            display:flex; align-items:center; justify-content:center;
            font-size:.8rem; flex-shrink:0;
        }
        .msg-avatar.bot    { background:rgba(0,229,255,.1);  border:1px solid rgba(0,229,255,.2); }
        .msg-avatar.user-av{ background:rgba(255,230,0,.1);  border:1px solid rgba(255,230,0,.2); }
        .bubble {
            max-width: 75%;
            padding: 11px 15px;
            border-radius: 13px;
            font-size: .86rem; line-height: 1.6;
        }
        .bubble.bot-b  { background:rgba(0,229,255,.07);  border:1px solid rgba(0,229,255,.15);  color:rgba(200,230,255,.9);  border-bottom-left-radius:4px; }
        .bubble.user-b { background:rgba(255,230,0,.08);  border:1px solid rgba(255,230,0,.15);  color:rgba(255,240,150,.9);  border-bottom-right-radius:4px; }
        .typing-b { background:rgba(0,229,255,.06); border:1px solid rgba(0,229,255,.12); }
        .typing-dots { display:flex; gap:4px; align-items:center; height:18px; }
        .typing-dots span { width:6px;height:6px; border-radius:50%; background:var(--cyan); animation:typing 1.4s infinite; }
        .typing-dots span:nth-child(2){animation-delay:.2s}
        .typing-dots span:nth-child(3){animation-delay:.4s}
        @keyframes typing { 0%,60%,100%{opacity:.2;transform:scale(.8)} 30%{opacity:1;transform:scale(1.1)} }
        .chat-input-area {
            padding: 14px 18px;
            border-top: 1px solid rgba(0,229,255,.1);
            display: flex; gap: 9px;
            background: rgba(0,10,30,.5);
            flex-shrink: 0;
        }
        #userInput {
            flex: 1;
            background: rgba(0,10,30,.8);
            border: 1px solid rgba(0,229,255,.2);
            border-radius: 10px;
            padding: 10px 15px;
            color: #c8e6ff;
            font-family: 'Rajdhani', sans-serif;
            font-size: .9rem; outline: none;
            transition: border-color .2s;
        }
        #userInput:focus { border-color:rgba(0,229,255,.5); }
        #userInput::placeholder { color:rgba(200,230,255,.3); }
        .send-btn {
            background: linear-gradient(135deg,rgba(0,229,255,.15),rgba(0,229,255,.05));
            border: 1px solid rgba(0,229,255,.3);
            border-radius: 10px; padding: 10px 17px;
            color: var(--cyan); cursor: pointer;
            font-size: .95rem; transition: all .2s;
        }
        .send-btn:hover { background:rgba(0,229,255,.2); border-color:var(--cyan); }
        .chat-sidebar-panel { display:flex; flex-direction:column; gap:12px; overflow-y:auto; }
        .quick-panel {
            background: var(--bg-panel);
            border: 1px solid rgba(0,229,255,.12);
            border-radius: 14px; padding: 16px;
            backdrop-filter: blur(10px);
        }
        .quick-panel h4 {
            font-family: 'Orbitron',monospace;
            font-size:.68rem; color:var(--cyan);
            letter-spacing:2px; text-transform:uppercase; margin-bottom:10px;
        }
        .quick-btn {
            width:100%; text-align:left;
            background:rgba(0,229,255,.04);
            border:1px solid rgba(0,229,255,.12);
            border-radius:8px; padding:9px 11px;
            color:rgba(200,230,255,.7); font-size:.78rem;
            cursor:pointer; margin-bottom:6px;
            transition:all .2s;
            font-family:'Rajdhani',sans-serif; letter-spacing:.4px;
        }
        .quick-btn:hover { background:rgba(0,229,255,.1); color:var(--cyan); border-color:rgba(0,229,255,.3); }
        .quick-btn:last-child { margin-bottom:0; }
        .context-panel {
            background: var(--bg-panel);
            border: 1px solid rgba(0,255,157,.15);
            border-radius: 14px; padding: 16px;
        }
        .context-panel h4 {
            font-family:'Orbitron',monospace;
            font-size:.68rem; color:var(--green);
            letter-spacing:2px; text-transform:uppercase; margin-bottom:10px;
        }
        .ctx-row {
            display:flex; justify-content:space-between; align-items:center;
            padding:6px 0; border-bottom:1px solid rgba(0,229,255,.07); font-size:.76rem;
        }
        .ctx-row:last-child { border-bottom:none; }
        .ctx-label { color:rgba(200,230,255,.45); }
        .ctx-val   { font-family:'Orbitron',monospace; font-size:.7rem; color:var(--cyan); }

        /* ===== QUICK ACTIONS (mobile chat) ===== */
        .quick-actions-scroll {
            display: none;
            overflow-x: auto;
            gap: 8px;
            padding-bottom: 4px;
            margin-bottom: 10px;
            -webkit-overflow-scrolling: touch;
            scrollbar-width: none;
        }
        .quick-actions-scroll::-webkit-scrollbar { display:none; }
        .qa-chip {
            flex-shrink: 0;
            background: rgba(0,229,255,.06);
            border: 1px solid rgba(0,229,255,.2);
            border-radius: 20px;
            padding: 6px 14px;
            color: var(--cyan);
            font-size: .75rem;
            font-family: 'Rajdhani', sans-serif;
            cursor: pointer;
            white-space: nowrap;
            transition: all .2s;
        }
        .qa-chip:hover, .qa-chip:active { background:rgba(0,229,255,.15); }

        /* ===================================
           RESPONSIVE BREAKPOINTS
        =================================== */

        /* ── TABLET (768–1023px) ── */
        @media (max-width: 1023px) and (min-width: 768px) {
            :root { --sidebar-w: 200px; }
            #main { padding: 20px; }
            .metric-value { font-size: 1.45rem; }
            .chat-layout { grid-template-columns: 1fr; height: auto; min-height: 0; }
            .chat-main { height: 55vh; min-height: 380px; }
            .chat-sidebar-panel { flex-direction: row; gap: 12px; }
            .quick-panel, .context-panel { flex: 1; }
            .quick-actions-scroll { display:flex; }
            .chat-sidebar-right { display:none; }
        }

        /* ── MOBILE (< 768px) ── */
        @media (max-width: 767px) {
            #sidebar    { display: none !important; }
            #bottom-nav { display: block !important; }

            #main {
                margin-left: 0;
                padding: 14px 12px;
                padding-bottom: calc(var(--nav-h) + 14px);
            }

            .page-header { margin-bottom: 14px; padding-bottom: 12px; }
            .page-header h1 { font-size:.95rem; letter-spacing:2px; }
            .page-header p  { font-size:.75rem; }

            .status-bar { padding:10px 14px; gap:8px; border-radius:10px; margin-bottom:14px; }
            .status-text { font-size:.75rem; }
            .status-time { font-size:.65rem; }

            /* metric cards: 1 column on phone */
            .metric-cards {
                grid-template-columns: 1fr;
                gap: 10px; margin-bottom: 14px;
            }
            /* each card row style on phone */
            .metric-card {
                padding: 14px 16px;
                display: flex;
                align-items: center;
                gap: 16px;
                border-radius: 14px;
            }
            .metric-card .glow-bg { width:70px; height:70px; top:-10px; right:-10px; }
            .metric-card-left { flex: 1; }
            .metric-value { font-size: 1.8rem; margin-bottom: 2px; }
            .metric-label { margin-bottom: 2px; }
            .metric-name  { margin-bottom: 4px; }

            /* calc grid: 2 col on phone */
            .calc-grid {
                grid-template-columns: repeat(2, 1fr);
                gap: 9px;
            }
            .calc-box { padding: 11px 8px; }
            .calc-val { font-size:.95rem; }

            .panel { padding: 14px; border-radius: 14px; margin-bottom: 14px; }

            /* charts: full width, taller */
            canvas { max-height: 160px !important; }
            .chart-wrap { padding:14px 12px 10px; margin-bottom:12px; }

            /* chat: full screen style */
            .chat-layout {
                grid-template-columns: 1fr;
                height: auto; gap: 12px;
            }
            .chat-main {
                height: calc(100dvh - var(--nav-h) - 180px);
                min-height: 340px;
                border-radius: 14px;
            }
            .chat-sidebar-right { display: none; }
            .quick-actions-scroll { display: flex; }
            .bubble { max-width: 85%; }
        }

        /* ── SMALL PHONE (< 390px) ── */
        @media (max-width: 390px) {
            .metric-value { font-size: 1.55rem; }
            .calc-val { font-size:.85rem; }
            .page-header h1 { font-size:.85rem; }
        }

        /* ── LARGE DESKTOP (≥ 1400px) ── */
        @media (min-width: 1400px) {
            #main { padding: 36px 40px; }
            .metric-value { font-size: 2rem; }
            .calc-grid { grid-template-columns: repeat(6, 1fr); }
        }
    </style>
</head>
<body>

<!-- ======== SIDEBAR (tablet + desktop) ======== -->
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

<!-- ======== BOTTOM NAV (mobile) ======== -->
<nav id="bottom-nav">
    <div class="bottom-nav-inner">
        <div class="bnav-item active" onclick="switchPage('home', null, this)">
            <span class="bni">🏠</span>
            <span>Trang Chủ</span>
        </div>
        <div class="bnav-item" onclick="switchPage('charts', null, this)">
            <span class="bni">📈</span>
            <span>Biểu Đồ</span>
        </div>
        <div class="bnav-item" onclick="switchPage('chat', null, this)">
            <span class="bni">🤖</span>
            <span>Chatbot</span>
        </div>
    </div>
</nav>

<!-- ======== MAIN ======== -->
<main id="main">

    <!-- ── TRANG CHỦ ── -->
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

        <!-- Metric Cards -->
        <div class="metric-cards">
            <div class="metric-card card-I">
                <div class="glow-bg"></div>
                <div class="metric-card-left">
                    <div class="metric-label">⚡ Dòng Điện</div>
                    <div class="metric-name">Cường độ dòng điện I</div>
                    <div class="metric-value" id="valI">—</div>
                    <div class="metric-unit">AMPERE (A)</div>
                </div>
            </div>
            <div class="metric-card card-U1">
                <div class="glow-bg"></div>
                <div class="metric-card-left">
                    <div class="metric-label">🔋 Điện Áp 1</div>
                    <div class="metric-name">Hiệu điện thế U₁</div>
                    <div class="metric-value" id="valU1">—</div>
                    <div class="metric-unit">VOLT (V)</div>
                </div>
            </div>
            <div class="metric-card card-U2">
                <div class="glow-bg"></div>
                <div class="metric-card-left">
                    <div class="metric-label">🔋 Điện Áp 2</div>
                    <div class="metric-name">Hiệu điện thế U₂</div>
                    <div class="metric-value" id="valU2">—</div>
                    <div class="metric-unit">VOLT (V)</div>
                </div>
            </div>
        </div>

        <!-- Thông số tính toán -->
        <div class="panel">
            <div class="panel-title">📊 Thông Số Tính Toán</div>
            <div class="calc-grid">
                <div class="calc-box">
                    <div class="calc-label">P₁ = U₁×I</div>
                    <div class="calc-val" style="color:var(--pink);" id="calcP1">—</div>
                    <div class="calc-unit">Watt (W)</div>
                </div>
                <div class="calc-box">
                    <div class="calc-label">R₁ = U₁/I</div>
                    <div class="calc-val" style="color:var(--orange);" id="calcR1">—</div>
                    <div class="calc-unit">Ohm (Ω)</div>
                </div>
                <div class="calc-box">
                    <div class="calc-label">Q₁ = P₁×t</div>
                    <div class="calc-val" style="color:var(--green);" id="calcQ1">—</div>
                    <div class="calc-unit">Joule (J)</div>
                </div>
                <div class="calc-box">
                    <div class="calc-label">P₂ = U₂×I</div>
                    <div class="calc-val" style="color:var(--pink);" id="calcP2">—</div>
                    <div class="calc-unit">Watt (W)</div>
                </div>
                <div class="calc-box">
                    <div class="calc-label">R₂ = U₂/I</div>
                    <div class="calc-val" style="color:var(--red);" id="calcR2">—</div>
                    <div class="calc-unit">Ohm (Ω)</div>
                </div>
                <div class="calc-box">
                    <div class="calc-label">Q₂ = P₂×t</div>
                    <div class="calc-val" style="color:var(--teal);" id="calcQ2">—</div>
                    <div class="calc-unit">Joule (J)</div>
                </div>
            </div>
        </div>

        <!-- Samples + Drift -->
        <div class="panel">
            <div class="stat-grid">
                <div class="stat-box">
                    <div class="stat-label">Số điểm đã nhận</div>
                    <div class="stat-val" style="font-size:1.5rem;color:var(--green);" id="calcCount">0</div>
                    <div class="stat-unit">Samples</div>
                </div>
                <div class="stat-box">
                    <div class="stat-label">Vận tốc drift V</div>
                    <div class="stat-val" style="font-size:1.1rem;color:var(--cyan);" id="calcV">—</div>
                    <div class="stat-unit">× 10⁻⁵ m/s</div>
                </div>
            </div>
        </div>
    </div>

    <!-- ── BIỂU ĐỒ ── -->
    <div class="page" id="page-charts">
        <div class="page-header">
            <h1>📈 Biểu Đồ Dữ Liệu</h1>
            <p>7 biểu đồ · Lịch sử tối đa 60 điểm gần nhất</p>
        </div>

        <div class="chart-section-badge" style="background:rgba(0,229,255,.06);border:1px solid rgba(0,229,255,.15);color:var(--cyan);">
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

        <div class="chart-section-badge" style="background:rgba(255,140,0,.06);border:1px solid rgba(255,140,0,.2);color:var(--orange);margin-top:8px;">
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

        <div class="chart-section-badge" style="background:rgba(0,255,157,.06);border:1px solid rgba(0,255,157,.2);color:var(--green);margin-top:8px;">
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

    <!-- ── CHATBOT ── -->
    <div class="page" id="page-chat">
        <div class="page-header">
            <h1>🤖 Chatbot Điện Học</h1>
            <p>Hỏi về I, U, P, R, Q và phân tích số liệu thời gian thực</p>
        </div>

        <!-- Quick action chips (mobile/tablet) -->
        <div class="quick-actions-scroll" id="quickChips">
            <div class="qa-chip" onclick="quickAsk('Cường độ dòng điện là gì?')">⚡ Dòng điện?</div>
            <div class="qa-chip" onclick="quickAsk('Công thức tính công suất điện?')">⚡ Công suất P?</div>
            <div class="qa-chip" onclick="quickAsk('Điện trở R là gì?')">📐 Điện trở R?</div>
            <div class="qa-chip" onclick="quickAsk('Nhiệt lượng Q là gì?')">🌡️ Nhiệt lượng Q?</div>
            <div class="qa-chip" onclick="quickAskWithData()">📊 Phân tích số liệu</div>
            <div class="qa-chip" onclick="quickAsk('Định luật Ohm là gì?')">📐 Định luật Ohm</div>
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

            <!-- sidebar (desktop only) -->
            <div class="chat-sidebar-right chat-sidebar-panel">
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
// Force HTTPS
if (location.protocol !== 'https:' && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1') {
    location.replace('https:' + location.href.substring(location.protocol.length));
}

// ===== NAVIGATION =====
function switchPage(name, sidebarEl, bottomEl) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.getElementById('page-' + name).classList.add('active');

    // sidebar active
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    if (sidebarEl) sidebarEl.classList.add('active');
    else {
        // find matching sidebar item
        document.querySelectorAll('.nav-item').forEach(n => {
            if (n.getAttribute('onclick') && n.getAttribute('onclick').includes("'" + name + "'")) {
                n.classList.add('active');
            }
        });
    }

    // bottom nav active
    document.querySelectorAll('.bnav-item').forEach(b => b.classList.remove('active'));
    if (bottomEl) bottomEl.classList.add('active');
    else {
        document.querySelectorAll('.bnav-item').forEach(b => {
            if (b.getAttribute('onclick') && b.getAttribute('onclick').includes("'" + name + "'")) {
                b.classList.add('active');
            }
        });
    }

    // scroll to top on mobile
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ===== CHARTS =====
function makeChart(id, label, color) {
    const ctx = document.getElementById(id).getContext('2d');
    return new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: label, data: [],
                borderColor: color,
                backgroundColor: color + '15',
                borderWidth: 2,
                pointRadius: 2,
                pointBackgroundColor: color,
                tension: 0.4, fill: true
            }]
        },
        options: {
            responsive: true,
            animation: false,
            plugins: { legend: { display: false } },
            scales: {
                x: {
                    ticks: { color: 'rgba(200,230,255,0.35)', font: { size: 9 }, maxRotation: 0, maxTicksLimit: 6 },
                    grid:  { color: 'rgba(255,255,255,0.04)' }
                },
                y: {
                    ticks: { color: 'rgba(200,230,255,0.35)', font: { size: 9 } },
                    grid:  { color: 'rgba(255,255,255,0.06)' }
                }
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

// ===== FETCH DATA =====
let lastI=0, lastU1=0, lastU2=0, lastR1=0, lastR2=0, lastQ1=0, lastQ2=0;

async function fetchData() {
    try {
        const res = await fetch('/api/latest', {
            cache: 'no-store',
            headers: { 'Cache-Control': 'no-cache' }
        });
        const d = await res.json();

        lastI  = d.I  || 0;
        lastU1 = d.U1 || 0;
        lastU2 = d.U2 || 0;
        lastR1 = d.R1 || 0;
        lastR2 = d.R2 || 0;
        lastQ1 = d.Q1 || 0;
        lastQ2 = d.Q2 || 0;

        const P1 = lastI * lastU1;
        const P2 = lastI * lastU2;

        document.getElementById('valI').textContent  = lastI.toFixed(4);
        document.getElementById('valU1').textContent = lastU1.toFixed(4);
        document.getElementById('valU2').textContent = lastU2.toFixed(4);

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
            document.getElementById('statusTime').textContent = d.timestamp;
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

        const ts = d.timestamps;
        setChart(chartI,  ts, d.histI);
        setChart(chartU1, ts, d.histU1);
        setChart(chartU2, ts, d.histU2);
        setChart(chartR1, ts, d.histR1);
        setChart(chartR2, ts, d.histR2);
        setChart(chartQ1, ts, d.histQ1);
        setChart(chartQ2, ts, d.histQ2);

    } catch(e) {
        console.error(e);
        document.getElementById('statusDot').classList.add('offline');
        document.getElementById('statusText').textContent = 'Lỗi kết nối server';
    }
}

fetchData();
setInterval(fetchData, 1000);

// ===== CHATBOT =====
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
    row.appendChild(avatar);
    row.appendChild(bubble);
    chatBox.appendChild(row);
    chatBox.scrollTop = chatBox.scrollHeight;
}

function showTyping() {
    const chatBox = document.getElementById('chatBox');
    const row = document.createElement('div');
    row.className = 'msg-row'; row.id = 'typingIndicator';
    const av = document.createElement('div'); av.className = 'msg-avatar bot'; av.textContent = '🤖';
    const b  = document.createElement('div'); b.className = 'bubble typing-b';
    b.innerHTML = '<div class="typing-dots"><span></span><span></span><span></span></div>';
    row.appendChild(av); row.appendChild(b);
    chatBox.appendChild(row);
    chatBox.scrollTop = chatBox.scrollHeight;
}
function removeTyping() {
    const el = document.getElementById('typingIndicator');
    if (el) el.remove();
}

async function sendMessage() {
    const input = document.getElementById('userInput');
    const message = input.value.trim();
    if (!message) return;
    addMessage(message, true);
    input.value = '';
    showTyping();
    try {
        const res = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message })
        });
        const data = await res.json();
        removeTyping();
        addMessage(data.response, false);
    } catch(e) {
        removeTyping();
        addMessage('Lỗi kết nối chatbot. Thử lại sau nhé!', false);
    }
}

function quickAsk(text) {
    document.getElementById('userInput').value = text;
    sendMessage();
}

function quickAskWithData() {
    const P1 = (lastI * lastU1).toFixed(4);
    const P2 = (lastI * lastU2).toFixed(4);
    const msg = `Số liệu đo được: I=${lastI.toFixed(4)}A, U₁=${lastU1.toFixed(4)}V, U₂=${lastU2.toFixed(4)}V. Tính toán: P₁=${P1}W, R₁=${lastR1.toFixed(4)}Ω, Q₁=${lastQ1.toFixed(3)}J | P₂=${P2}W, R₂=${lastR2.toFixed(4)}Ω, Q₂=${lastQ2.toFixed(3)}J. Bạn hãy phân tích các giá trị này giúp tôi?`;
    document.getElementById('userInput').value = msg;
    sendMessage();
}

document.getElementById('userInput').addEventListener('keypress', e => {
    if (e.key === 'Enter') sendMessage();
});
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
    global Q1_total, Q2_total, last_recv_time
    try:
        d = request.get_json(force=True)
        I  = float(d.get('I',  0))
        U1 = float(d.get('U1', 0))
        U2 = float(d.get('U2', 0))
        V  = float(d.get('V',  0))
        ts = time.strftime('%H:%M:%S')

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
            "timestamp":  latest_data['timestamp'],
            "histI":      history_data['I'][-60:],
            "histU1":     history_data['U1'][-60:],
            "histU2":     history_data['U2'][-60:],
            "histR1":     history_data['R1'][-60:],
            "histR2":     history_data['R2'][-60:],
            "histQ1":     history_data['Q1'][-60:],
            "histQ2":     history_data['Q2'][-60:],
            "timestamps": history_data['timestamps'][-60:],
            "count":      len(history_data['I'])
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
    print('📡 Gửi JSON mẫu: {"I":0.1,"U1":3.3,"U2":5.0,"V":1.5e-5}')
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port, threaded=True, debug=False)