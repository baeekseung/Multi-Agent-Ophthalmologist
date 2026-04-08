"""
AGENTIC OPHTIMUS 아키텍처 다이어그램 생성 스크립트
"""
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import matplotlib.patheffects as pe
import numpy as np

fig, ax = plt.subplots(1, 1, figsize=(22, 28))
ax.set_xlim(0, 22)
ax.set_ylim(0, 28)
ax.axis('off')

# ── 배경 ──────────────────────────────────────────────────────────────
fig.patch.set_facecolor('#0D1117')
ax.set_facecolor('#0D1117')

# ── 색상 팔레트 ──────────────────────────────────────────────────────
C = {
    'bg':        '#0D1117',
    'panel':     '#161B22',
    'panel2':    '#1C2330',
    'border':    '#30363D',
    'blue':      '#58A6FF',
    'green':     '#3FB950',
    'purple':    '#BC8CFF',
    'orange':    '#F78166',
    'yellow':    '#E3B341',
    'cyan':      '#39D3F2',
    'teal':      '#56D364',
    'red':       '#FF7B72',
    'white':     '#E6EDF3',
    'gray':      '#8B949E',
    'dark_blue': '#0D2137',
    'dark_green':'#0D2318',
    'dark_purple':'#1A1040',
    'dark_orange':'#2D1206',
}

def rounded_box(ax, x, y, w, h, fc, ec, lw=1.5, alpha=1.0, radius=0.3):
    box = FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0,rounding_size={radius}",
        facecolor=fc, edgecolor=ec, linewidth=lw, alpha=alpha, zorder=3
    )
    ax.add_patch(box)
    return box

def label(ax, x, y, text, color, size=9, bold=False, ha='center', va='center', zorder=5):
    weight = 'bold' if bold else 'normal'
    ax.text(x, y, text, color=color, fontsize=size, fontweight=weight,
            ha=ha, va=va, zorder=zorder, fontfamily='monospace')

def arrow(ax, x1, y1, x2, y2, color, lw=1.5, style='->', dashed=False):
    ls = '--' if dashed else '-'
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle=style, color=color,
                                lw=lw, linestyle=ls),
                zorder=4)

def section_title(ax, x, y, text, color, size=10):
    ax.text(x, y, text, color=color, fontsize=size, fontweight='bold',
            ha='center', va='center', zorder=6, fontfamily='monospace',
            bbox=dict(boxstyle='round,pad=0.3', facecolor=C['bg'],
                      edgecolor=color, linewidth=1.2, alpha=0.9))


# ════════════════════════════════════════════════════════════════════════
# 타이틀
# ════════════════════════════════════════════════════════════════════════
ax.text(11, 27.3, 'AGENTIC OPHTIMUS', color=C['blue'],
        fontsize=20, fontweight='bold', ha='center', va='center',
        fontfamily='monospace')
ax.text(11, 26.8, 'AI-Powered Ophthalmic Diagnosis Agent Architecture',
        color=C['gray'], fontsize=11, ha='center', va='center', fontfamily='monospace')

# 구분선
ax.plot([0.5, 21.5], [26.5, 26.5], color=C['border'], lw=1)


# ════════════════════════════════════════════════════════════════════════
# LAYER 0 : 클라이언트
# ════════════════════════════════════════════════════════════════════════
rounded_box(ax, 0.5, 25.2, 21, 1.1, C['panel'], C['border'], lw=1)
label(ax, 1.5, 25.75, 'CLIENT', C['gray'], size=8)

for i, (lbl, clr) in enumerate([('Web Browser', C['cyan']),
                                  ('REST Client', C['cyan']),
                                  ('CLI (main.py)', C['yellow'])]):
    cx = 4.5 + i * 5
    rounded_box(ax, cx - 1.6, 25.3, 3.2, 0.85, C['dark_blue'], clr, lw=1.2)
    label(ax, cx, 25.72, lbl, clr, size=9, bold=True)


# ════════════════════════════════════════════════════════════════════════
# LAYER 1 : FastAPI Backend
# ════════════════════════════════════════════════════════════════════════
rounded_box(ax, 0.5, 22.8, 21, 2.2, C['panel'], C['border'], lw=1)
label(ax, 1.5, 23.9, 'FastAPI\nBackend', C['gray'], size=8)

# api/main.py 중앙
rounded_box(ax, 4.5, 23.1, 4, 1.5, C['dark_blue'], C['blue'], lw=1.5)
label(ax, 6.5, 24.1, 'api/main.py', C['blue'], size=9.5, bold=True)
label(ax, 6.5, 23.7, 'FastAPI App + Middleware', C['gray'], size=8)
label(ax, 6.5, 23.35, 'Lifespan + CORS + Logging', C['gray'], size=7.5)

# 라우터들
routers = [('GET /health', 'health.py', C['teal']),
           ('POST /sessions\nGET /sessions/{id}', 'sessions.py', C['blue']),
           ('GET /sessions/{id}/report', 'reports.py', C['purple'])]
for i, (ep, fn, clr) in enumerate(routers):
    rx = 10.2 + i * 3.5
    rounded_box(ax, rx, 23.1, 3.2, 1.5, C['dark_blue'], clr, lw=1.2)
    label(ax, rx + 1.6, 23.95, fn, clr, size=8.5, bold=True)
    label(ax, rx + 1.6, 23.55, ep, C['gray'], size=7.2)

# 화살표: 클라이언트 → FastAPI
arrow(ax, 11, 25.2, 11, 25.0, C['blue'], lw=2)

# 화살표: 라우터 연결
for i in range(3):
    arrow(ax, 8.5, 23.85, 10.2 + i * 3.5, 23.85, C['gray'], lw=1, dashed=True)


# ════════════════════════════════════════════════════════════════════════
# LAYER 2 : LangGraph 메인 워크플로우
# ════════════════════════════════════════════════════════════════════════
rounded_box(ax, 0.5, 7.0, 21, 15.6, C['panel2'], C['border'], lw=1)
label(ax, 1.8, 14.8, 'LangGraph\nMain\nWorkflow', C['gray'], size=8)

# FastAPI → LangGraph 화살표
arrow(ax, 6.5, 22.8, 6.5, 22.55, C['blue'], lw=2)

# ────────────────────────────────────────────────────────────────────────
# Part 1: Consultation
# ────────────────────────────────────────────────────────────────────────
rounded_box(ax, 1.0, 19.8, 10.5, 2.8, C['dark_blue'], C['blue'], lw=1.2, radius=0.25)
section_title(ax, 6.25, 22.4, 'Part 1 · Consultation', C['blue'], size=9)

nodes_p1 = [
    ('consultation\n_agent', 2.5, 20.8, C['blue']),
    ('patient\n_response\n(interrupt)', 5.8, 20.8, C['cyan']),
    ('summarize\n_consultation', 9.2, 20.8, C['blue']),
]
for lbl, nx, ny, clr in nodes_p1:
    rounded_box(ax, nx - 1.1, ny - 0.6, 2.2, 1.35, C['dark_blue'], clr, lw=1.3)
    label(ax, nx, ny, lbl, clr, size=8, bold=True)

# Part1 내부 화살표
arrow(ax, 3.6, 20.8, 4.7, 20.8, C['blue'])
arrow(ax, 6.9, 20.8, 8.1, 20.8, C['blue'])
# interrupt 루프
ax.annotate('', xy=(4.7, 21.4), xytext=(6.9, 21.4),
            arrowprops=dict(arrowstyle='<->', color=C['cyan'], lw=1.2))
label(ax, 5.8, 21.6, 'interrupt / resume', C['cyan'], size=7.5)

# ────────────────────────────────────────────────────────────────────────
# Part 2: Mid-Level Analysis
# ────────────────────────────────────────────────────────────────────────
rounded_box(ax, 1.0, 13.8, 19.5, 5.7, C['dark_purple'], C['purple'], lw=1.2, radius=0.25)
section_title(ax, 10.75, 19.3, 'Part 2 · Mid-Level Analysis (Multi-Expert Panel)', C['purple'], size=9)

# supervisor
rounded_box(ax, 1.5, 16.8, 2.8, 1.3, C['dark_purple'], C['purple'], lw=1.5)
label(ax, 2.9, 17.45, 'supervisor', C['purple'], size=9, bold=True)

# expert 3종
expert_colors = [C['blue'], C['green'], C['orange']]
for i, (en, clr) in enumerate(zip(['expert1\n(temp=0.1)', 'expert2\n(temp=0.5)', 'expert3\n(temp=0.9)'], expert_colors)):
    ex = 5.8 + i * 3.5
    rounded_box(ax, ex - 1.3, 16.7, 2.6, 1.4, C['panel'], clr, lw=1.3)
    label(ax, ex, 17.42, en, clr, size=8.5, bold=True)

# evaluate + summarize
rounded_box(ax, 15.5, 16.8, 2.5, 1.3, C['dark_purple'], C['purple'], lw=1.3)
label(ax, 16.75, 17.45, 'evaluate\n_consensus', C['purple'], size=8.5, bold=True)

rounded_box(ax, 15.5, 14.8, 2.5, 1.5, C['dark_purple'], C['yellow'], lw=1.3)
label(ax, 16.75, 15.58, 'summarize\n_consensus', C['yellow'], size=8.5, bold=True)

# supervisor → expert 화살표
for i in range(3):
    ex = 5.8 + i * 3.5
    arrow(ax, 4.3, 17.45, ex - 1.3, 17.45, C['purple'])

# expert → evaluate
for i in range(3):
    ex = 5.8 + i * 3.5
    arrow(ax, ex + 1.3, 17.1, 15.5, 17.1, C['gray'], dashed=True)

# evaluate → summarize
arrow(ax, 16.75, 16.8, 16.75, 16.3, C['purple'])

# evaluate → supervisor (재순환)
ax.annotate('', xy=(4.3, 15.2), xytext=(15.5, 15.2),
            arrowprops=dict(arrowstyle='<-', color=C['red'],
                            lw=1.2, linestyle='--', connectionstyle='arc3,rad=0'))
label(ax, 10.0, 14.9, 'INSUFFICIENT → reconsult (max 3 rounds)', C['red'], size=7.5)

# consensus 내부 라벨
label(ax, 10.0, 18.8, '[ Parallel Expert Opinions ]', C['gray'], size=8)

# ────────────────────────────────────────────────────────────────────────
# Part 3: Diagnosis Deep Agent
# ────────────────────────────────────────────────────────────────────────
rounded_box(ax, 1.0, 7.3, 19.5, 6.2, C['dark_green'], C['green'], lw=1.2, radius=0.25)
section_title(ax, 10.75, 13.3, 'Part 3 · Diagnosis Deep Agent (Orchestrator)', C['green'], size=9)

# diagnosis_agent
rounded_box(ax, 2.0, 9.8, 3.2, 1.5, C['dark_green'], C['green'], lw=1.5)
label(ax, 3.6, 10.58, 'diagnosis_agent', C['green'], size=9, bold=True)
label(ax, 3.6, 10.2, 'Orchestrator', C['gray'], size=7.5)
label(ax, 3.6, 9.88, 'write_todos / read_todos', C['gray'], size=7)

# TODO 관리
rounded_box(ax, 2.0, 7.7, 3.2, 1.6, C['panel'], C['yellow'], lw=1.2)
label(ax, 3.6, 8.75, 'TODO List', C['yellow'], size=8.5, bold=True)
label(ax, 3.6, 8.4, '1. gap_check', C['gray'], size=7.5)
label(ax, 3.6, 8.1, '2. guideline_retrieval', C['gray'], size=7.5)
label(ax, 3.6, 7.82, '3. report_writing', C['gray'], size=7.5)

arrow(ax, 3.6, 9.8, 3.6, 9.3, C['yellow'])

# 서브에이전트 4종
sub_agents = [
    ('deep_search\n_agent', C['cyan'],    'Tavily Search\n+ think_tool'),
    ('analysis\n_agent',    C['blue'],    'read_files\n+ analyze_tool'),
    ('organize\n_agent',    C['purple'],  'synthesize_tool\n+ submit_result'),
    ('write\n_agent',       C['orange'],  'draft_section\n+ submit_report'),
]
for i, (name, clr, sub) in enumerate(sub_agents):
    sx = 6.8 + i * 3.7
    rounded_box(ax, sx - 1.4, 9.5, 2.8, 2.0, C['panel'], clr, lw=1.3)
    label(ax, sx, 11.0, name, clr, size=8.5, bold=True)
    label(ax, sx, 10.6, sub, C['gray'], size=7.2)

    # 결과 파일
    if i < 3:
        file_names = ['gap_check\n_result.md', 'guideline\n_result.md', 'diagnosis\n_report.md']
        if i < len(file_names):
            fy = 8.1 if i < 2 else 8.1
            rounded_box(ax, sx - 1.3, 7.75, 2.6, 0.9, C['panel'], C['gray'], lw=0.8)
            label(ax, sx, 8.2, file_names[i], C['gray'], size=7)
            arrow(ax, sx, 9.5, sx, 8.65, C['gray'], lw=1, dashed=True)

    # diagnosis_agent → sub_agent
    arrow(ax, 5.2, 10.55, sx - 1.4, 10.55, C['green'], lw=1.2)

# write_agent → diagnosis_report (마지막)
sx_w = 6.8 + 3 * 3.7
rounded_box(ax, sx_w - 1.3, 7.75, 2.6, 0.9, C['panel'], C['orange'], lw=1)
label(ax, sx_w, 8.2, 'diagnosis\n_report.md', C['orange'], size=7)
arrow(ax, sx_w, 9.5, sx_w, 8.65, C['orange'], lw=1, dashed=True)


# ════════════════════════════════════════════════════════════════════════
# LAYER 3 : Database
# ════════════════════════════════════════════════════════════════════════
rounded_box(ax, 0.5, 3.8, 10, 3.0, C['panel'], C['border'], lw=1)
section_title(ax, 5.5, 6.65, 'PostgreSQL Database', C['yellow'], size=9)

rounded_box(ax, 1.0, 4.1, 4.2, 2.2, C['panel'], C['yellow'], lw=1.2)
label(ax, 3.1, 5.45, 'PatientRecord', C['yellow'], size=9, bold=True)
label(ax, 3.1, 5.1, 'session_id, status', C['gray'], size=7.8)
label(ax, 3.1, 4.75, 'consultation_data', C['gray'], size=7.8)
label(ax, 3.1, 4.4, 'final_report', C['gray'], size=7.8)

rounded_box(ax, 5.8, 4.1, 4.2, 2.2, C['panel'], C['orange'], lw=1.2)
label(ax, 7.9, 5.45, 'SessionStore', C['orange'], size=9, bold=True)
label(ax, 7.9, 5.1, 'thread_id, graph', C['gray'], size=7.8)
label(ax, 7.9, 4.75, 'LangGraph State', C['gray'], size=7.8)
label(ax, 7.9, 4.4, '(MemorySaver)', C['gray'], size=7.8)

# ════════════════════════════════════════════════════════════════════════
# LAYER 4 : External Services
# ════════════════════════════════════════════════════════════════════════
rounded_box(ax, 11.5, 3.8, 10, 3.0, C['panel'], C['border'], lw=1)
section_title(ax, 16.5, 6.65, 'External Services', C['red'], size=9)

ext = [('OpenAI GPT-4o', C['blue'],   'LLM Backbone'),
       ('Tavily Search', C['cyan'],   'Web Search API'),
       ('ChromaDB\n(planned)', C['purple'], 'Vector Store')]
for i, (name, clr, sub) in enumerate(ext):
    ex = 12.5 + i * 3.2
    rounded_box(ax, ex, 4.1, 2.8, 2.2, C['panel'], clr, lw=1.2)
    label(ax, ex + 1.4, 5.45, name, clr, size=8, bold=True)
    label(ax, ex + 1.4, 5.0, sub, C['gray'], size=7.5)

# ════════════════════════════════════════════════════════════════════════
# 레이어 간 주요 화살표
# ════════════════════════════════════════════════════════════════════════
# FastAPI → LangGraph (sessions)
arrow(ax, 11.8, 22.8, 6.5, 22.55, C['blue'], lw=2)

# Part1 → Part2
arrow(ax, 9.2, 20.2, 9.2, 19.5, C['blue'], lw=1.5)
label(ax, 10.5, 19.8, 'consultation_summary', C['gray'], size=7.5)

# Part2 → Part3 (SUFFICIENT)
arrow(ax, 16.75, 14.8, 16.75, 14.3, C['green'], lw=1.5)
ax.annotate('', xy=(3.6, 13.5), xytext=(16.75, 13.5),
            arrowprops=dict(arrowstyle='->', color=C['green'], lw=1.5))
arrow(ax, 3.6, 13.5, 3.6, 11.3, C['green'], lw=1.5)
label(ax, 10.0, 13.7, 'SUFFICIENT → diagnosis_agent', C['green'], size=8)

# Part3 → DB
arrow(ax, 3.6, 7.3, 3.6, 6.3, C['yellow'], lw=1.5)

# Part3 → External
arrow(ax, 17.0, 7.3, 17.0, 6.3, C['blue'], lw=1.5, dashed=True)
label(ax, 17.5, 6.6, 'API calls', C['gray'], size=7)


# ════════════════════════════════════════════════════════════════════════
# 범례
# ════════════════════════════════════════════════════════════════════════
rounded_box(ax, 0.5, 0.2, 21, 3.4, C['panel'], C['border'], lw=1)
label(ax, 1.5, 3.3, 'LEGEND', C['gray'], size=8, bold=True, ha='left')

legend_items = [
    (C['blue'],   'FastAPI / LLM Node'),
    (C['cyan'],   'Interrupt / IO'),
    (C['purple'], 'Multi-Expert'),
    (C['green'],  'Deep Agent'),
    (C['yellow'], 'Database / TODO'),
    (C['orange'], 'Output Files'),
    (C['red'],    'Error / Loop Back'),
    (C['gray'],   'Internal Flow (dashed)'),
]
for i, (clr, txt) in enumerate(legend_items):
    col = i % 4
    row = i // 4
    lx = 1.5 + col * 5.2
    ly = 2.6 - row * 1.0
    rounded_box(ax, lx - 0.1, ly - 0.25, 0.55, 0.5, C['panel'], clr, lw=1.5)
    label(ax, lx + 0.9, ly, txt, C['white'], size=8, ha='left')

# 버전 / 날짜
label(ax, 21, 0.35, 'v1.0 · 2026-04-08', C['gray'], size=7.5, ha='right')

plt.tight_layout(pad=0.2)
plt.savefig('architecture.png', dpi=180, bbox_inches='tight',
            facecolor=C['bg'], edgecolor='none')
print("architecture.png 저장 완료")
plt.close()
