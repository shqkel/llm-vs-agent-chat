"""LLM Only vs Agent 비교 채팅 (수업용)

- LLM Only : 모델에 이번 질문 하나만 보낸다. 이전 대화·오늘 날짜·웹검색·파일첨부 없음.
- Agent    : 이전 대화(Chat History), 날짜·시간 도구, 웹검색, 파일첨부를 켜고 끌 수 있다.
             Chat History 를 켜면 다음 요청에 함께 보내지는 메시지를 노란색으로 표시한다.
"""

import base64
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import anthropic
import streamlit as st

ENABLED_FAMILIES = ["haiku"]          # 수업에서 고를 수 있는 모델 계열
FAMILIES = ["haiku", "sonnet", "opus", "fable"]
IMAGE_TYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
               "gif": "image/gif", "webp": "image/webp"}
TEXT_TYPES = ["txt", "md", "csv", "json", "py", "html", "xml", "yaml", "yml", "log"]
MAX_FILE_MB = 10
MAX_AGENT_STEPS = 8
TZ = ZoneInfo("Asia/Seoul")

st.set_page_config(page_title="LLM vs Agent 채팅", page_icon="💬")
st.markdown("""
<style>
div[class*="st-key-sent-"] {
    background: #FFF6D1; border-left: 5px solid #F2B600;
    border-radius: 8px; padding: 2px 10px;
}
</style>
""", unsafe_allow_html=True)


def secret(key):
    """secrets.toml 이 아예 없어도 죽지 않게 읽는다."""
    try:
        return st.secrets.get(key)
    except Exception:
        return None


# ── 접속 코드 (secrets 에 APP_PASSWORD 가 있을 때만) ─────────────────
password = secret("APP_PASSWORD")
if password and not st.session_state.get("authed"):
    st.title("💬 LLM vs Agent 채팅")
    code = st.text_input("접속 코드", type="password")
    if code:
        if code == password:
            st.session_state.authed = True
            st.rerun()
        st.error("접속 코드가 틀렸습니다.")
    st.stop()

api_key = secret("ANTHROPIC_API_KEY")
if not api_key:
    st.error("ANTHROPIC_API_KEY 가 설정되지 않았습니다. (Streamlit Cloud → Settings → Secrets)")
    st.stop()
# 워크스페이스에 묶이지 않은 키(sk-ant-usr…)는 워크스페이스 ID 헤더가 필요하다.
workspace_id = secret("ANTHROPIC_WORKSPACE_ID")
client = anthropic.Anthropic(
    api_key=api_key,
    default_headers={"anthropic-workspace-id": workspace_id} if workspace_id else None,
)


@st.cache_data(ttl=3600, show_spinner=False)
def latest_models():
    """계열별 최신 모델 {family: (id, display_name)} — 앱 구동 시점에 API 에서 조회."""
    latest = {}
    try:
        for m in client.models.list():
            fam = next((f for f in FAMILIES if f in m.id), None)
            if fam and (fam not in latest or m.created_at > latest[fam][2]):
                latest[fam] = (m.id, m.display_name, m.created_at)
    except anthropic.APIError:
        pass
    if "haiku" not in latest:  # 목록 조회 실패 시 대비
        latest["haiku"] = ("claude-haiku-5-5", "Claude Haiku 5.5", None)
    return {f: (v[0], v[1]) for f, v in latest.items()}


# 파일첨부는 두 모드 모두 항상 허용 — 이미지·PDF 읽기는 모델 자체 입력 기능이다
use_files = True

# ── 사이드바 ─────────────────────────────────────────────────────
models = latest_models()
with st.sidebar:
    st.header("설정")
    # 활성 계열을 앞에, 비활성 계열을 뒤에 둔다 — 비활성 항목은 드롭다운에 보이되 회색·클릭 불가(CSS)
    enabled = [f for f in FAMILIES if f in models and f in ENABLED_FAMILIES]
    locked = [f for f in FAMILIES if f in models and f not in ENABLED_FAMILIES]
    locked_css = ", ".join(f'[role="listbox"][aria-label="모델 (최신)"] [role="option"][aria-posinset="{i}"]'
                           for i in range(len(enabled) + 1, len(enabled) + len(locked) + 1))
    if locked_css:
        st.markdown(f"<style>{locked_css} {{ opacity: .4; pointer-events: none; }}</style>",
                    unsafe_allow_html=True)
    fam = st.selectbox("모델 (최신)", enabled + locked, key="model_family",
                       format_func=lambda f: models[f][1] + ("" if f in enabled else " 🔒"))
    if fam not in enabled:   # CSS 가 안 먹는 환경 대비 — 비활성은 고를 수 없게 되돌린다
        st.warning(f"{models[fam][1]} 은(는) 비활성 모델입니다. {models[enabled[0]][1]} 로 진행합니다.")
        fam = enabled[0]
    model_id = models[fam][0]

    mode = st.radio("모드", ["LLM Only", "Agent"], horizontal=True)
    agent = mode == "Agent"
    if agent:
        st.info("**Agent** — 모델이 도구를 써서 스스로 확인하고 답합니다.\n\n"
                "이전 대화를 함께 보내 기억하고, 오늘 날짜를 직접 확인하고, 웹을 검색합니다. "
                "아래 토글로 하나씩 꺼 보며 무엇이 달라지는지 비교하세요.")
        use_history = st.toggle("💬 Chat History (이전 대화 기억)", True)
        history_turns = st.slider("함께 보낼 이전 대화 (최근 몇 턴)", 1, 10, 3,
                                  disabled=not use_history)
        use_clock = st.toggle("📅 날짜·시간 확인", True)
        use_search = st.toggle("🌐 웹검색", True)
    else:
        use_history = use_clock = use_search = False
        history_turns = 0
        st.info("**LLM Only** — 이번 질문만 보냅니다.\n\n"
                "이전 대화를 모르고, 오늘 날짜도 모르고, 검색도 못 합니다.\n\n"
                "📎 파일첨부는 됩니다 — 이미지·PDF 를 읽는 건 모델 자체 기능입니다. "
                "다만 스스로 찾아오지는 못하고, 건네준 것만 읽습니다.")
    system_prompt = st.text_area("시스템 프롬프트 (선택)", "", height=80)
    max_tokens = st.slider("최대 출력 토큰", 1024, 8192, 2048, step=512)
    if st.button("대화 지우기"):
        st.session_state.history = []
        st.rerun()

st.title("💬 LLM vs Agent 채팅")
st.caption(f"모드: **{mode}** · 모델: `{model_id}`")

# ── 도구 ─────────────────────────────────────────────────────────
CLOCK_TOOL = {
    "name": "get_current_datetime",
    "description": "지금 한국 시각(Asia/Seoul)의 날짜·요일·시간을 알려준다. "
                   "오늘 날짜나 현재 시각이 필요한 질문이면 반드시 이 도구로 확인한다.",
    "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
}
# Haiku 는 기본 웹검색(20250305) — 동적 필터링판(20260209)은 Opus·Sonnet 용이라
# Haiku 에서는 검색어 형식을 틀리는 일이 있다(2026-10-11 실측).
SEARCH_TOOL = {"type": "web_search_20250305" if fam == "haiku" else "web_search_20260209",
               "name": "web_search", "max_uses": 3}


def run_client_tool(name, _input):
    if name == "get_current_datetime":
        now = datetime.now(TZ)
        week = "월화수목금토일"[now.weekday()]
        return now.strftime(f"%Y-%m-%d ({week}) %H:%M:%S KST")
    return f"알 수 없는 도구: {name}"


def to_block(f):
    """업로드 파일 → Claude 콘텐츠 블록. 지원 안 하면 None."""
    ext = f.name.rsplit(".", 1)[-1].lower()
    data = f.getvalue()
    if len(data) > MAX_FILE_MB * 1024 * 1024:
        st.warning(f"{f.name}: {MAX_FILE_MB}MB 를 넘어 제외했습니다.")
        return None
    if ext in IMAGE_TYPES:
        return {"type": "image", "source": {"type": "base64", "media_type": IMAGE_TYPES[ext],
                                            "data": base64.b64encode(data).decode()}}
    if ext == "pdf":
        return {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                               "data": base64.b64encode(data).decode()}}
    if ext in TEXT_TYPES:
        return {"type": "text", "text": f"[첨부 파일: {f.name}]\n{data.decode('utf-8', 'replace')}"}
    st.warning(f"{f.name}: 지원하지 않는 형식이라 제외했습니다.")
    return None


def history_window(history):
    """다음 요청에 함께 보낼 이전 메시지의 인덱스 (최근 N턴)."""
    if not use_history:
        return set()
    return set(range(max(0, len(history) - history_turns * 2), len(history)))


def as_message(msg):
    """화면 기록 1건 → API 메시지 (이전 턴은 텍스트로만 보낸다)."""
    text = msg["content"]
    if msg.get("files"):
        text += "\n[이때 첨부했던 파일: " + ", ".join(msg["files"]) + "]"
    if msg.get("tool_log"):   # 도구로 얻은 값을 '추측'으로 오해하지 않게 함께 보낸다
        text += "\n[이 답변에서 사용한 도구: " + "; ".join(msg["tool_log"]) + "]"
    return {"role": msg["role"], "content": text}


def preview(messages):
    """'실제로 보낸 messages' 표시용 — base64 는 줄여서 보여 준다."""
    def short(block):
        if isinstance(block, dict) and block.get("type") in ("image", "document"):
            return {"type": block["type"], "source": "…(base64 생략)…"}
        return block
    out = []
    for m in messages:
        c = m["content"]
        out.append({"role": m["role"], "content": c if isinstance(c, str) else [short(b) for b in c]})
    return json.dumps(out, ensure_ascii=False, indent=2)


# ── 화면 기록 ─────────────────────────────────────────────────────
if "history" not in st.session_state:
    st.session_state.history = []
history = st.session_state.history
will_send = history_window(history)


def render(i, msg):
    with st.chat_message(msg["role"]):
        box = st.container(key=f"sent-{i}") if i in will_send else st.container()
        with box:
            if i in will_send:
                st.caption("📤 다음 요청에 함께 전송")
            st.markdown(msg["content"])
            if msg.get("files"):
                st.caption("📎 " + ", ".join(msg["files"]))
        if msg.get("steps"):
            with st.expander(f"🔧 에이전트 동작 {len(msg['steps'])}건"):
                for s in msg["steps"]:
                    st.markdown(s)
        if msg.get("sent"):
            with st.expander(f"📨 이 답변을 위해 보낸 messages ({msg['sent_count']}개)"):
                st.code(msg["sent"], language="json")


for i, msg in enumerate(history):
    render(i, msg)

if agent and use_history and will_send:
    st.caption(f"🟨 노란 메시지 {len(will_send)}개가 다음 질문과 함께 모델에 보내집니다.")

# ── 테스트 질문 추천 (누르면 입력창에 채워진다) ─────────────────────────
st.caption("💡 테스트 질문 — 누르면 입력창에 채워집니다. 같은 질문을 두 모드에서 비교해 보세요.")
SUGGESTIONS = [
    ("🧠 기억 1", "내 이름은 철수야. 기억해 줘."),
    ("🧠 기억 2", "내 이름이 뭐였지?"),
    ("📅 날짜", "오늘 몇 월 며칠 무슨 요일이야?"),
    ("🌐 검색", "오늘 서울 날씨를 검색해서 알려줘."),
    ("🌐 최신 뉴스", "이번 주 AI 관련 주요 뉴스 3개를 출처와 함께 알려줘."),
    ("📎 파일", "첨부한 파일 내용을 3줄로 요약해 줘."),
]


def fill_input(text):
    st.session_state.chat = text


with st.container(horizontal=True):
    for label, text in SUGGESTIONS:
        st.button(label, help=text, on_click=fill_input, args=(text,))

prompt = st.chat_input(
    "메시지를 입력하세요",
    key="chat",
    accept_file="multiple" if use_files else False,
    file_type=(list(IMAGE_TYPES) + ["pdf"] + TEXT_TYPES) if use_files else None,
)

if prompt:
    text = prompt if isinstance(prompt, str) else (prompt.text or "")
    files = [] if isinstance(prompt, str) else (prompt.files or [])
    file_names = [f.name for f in files]

    # 이번 요청 messages: (Agent+History 면) 이전 대화 + 이번 질문
    prior = [as_message(history[i]) for i in sorted(will_send)]
    content = [b for b in (to_block(f) for f in files) if b]
    content.append({"type": "text", "text": text or "첨부한 파일을 설명해 주세요."})
    messages = prior + [{"role": "user", "content": content}]
    sent_preview, sent_count = preview(messages), len(messages)

    user_msg = {"role": "user", "content": text or "_(파일만 첨부)_", "files": file_names}
    history.append(user_msg)
    if agent and use_history:                     # 지금 보내는 질문도 노란색 (LLM Only 는 표시 없음)
        will_send = will_send | {len(history) - 1}
    render(len(history) - 1, user_msg)

    tools = ([CLOCK_TOOL] if use_clock else []) + ([SEARCH_TOOL] if use_search else [])
    kwargs = dict(model=model_id, max_tokens=max_tokens)
    if tools:
        kwargs["tools"] = tools
    if system_prompt.strip():
        kwargs["system"] = system_prompt.strip()

    steps, tool_log, answer = [], [], ""
    with st.chat_message("assistant"):
        placeholder = st.empty()
        status = st.empty()
        try:
            for _ in range(MAX_AGENT_STEPS):
                with client.messages.stream(messages=messages, **kwargs) as stream:
                    for chunk in stream.text_stream:
                        answer += chunk
                        placeholder.markdown(answer + "▌")
                    final = stream.get_final_message()

                tool_results = []
                for b in final.content:
                    if b.type == "server_tool_use" and b.name == "web_search":
                        q = b.input.get("query") or b.input.get("params", {}).get("query", "")
                        steps.append(f"🌐 웹검색: `{q}`")
                        tool_log.append(f"web_search({q})")
                    elif b.type == "web_search_tool_result" and isinstance(b.content, list):
                        for r in b.content[:3]:
                            steps.append(f"　└ [{r.title}]({r.url})")
                    elif b.type == "tool_use":
                        result = run_client_tool(b.name, b.input)
                        steps.append(f"📅 `{b.name}` → {result}")
                        tool_log.append(f"{b.name} → {result}")
                        tool_results.append({"type": "tool_result", "tool_use_id": b.id,
                                             "content": result})

                if final.stop_reason == "tool_use":
                    status.caption("🔧 도구 사용 중…")
                    messages = messages + [{"role": "assistant", "content": final.content},
                                           {"role": "user", "content": tool_results}]
                    answer += "\n\n" if answer else ""
                    continue
                if final.stop_reason == "pause_turn":   # 서버 도구(웹검색)가 길어 잠깐 멈춤
                    messages = messages + [{"role": "assistant", "content": final.content}]
                    continue
                if final.stop_reason == "max_tokens":
                    answer += "\n\n_(최대 출력 토큰에 도달해 답이 잘렸습니다)_"
                break
        except anthropic.APIError as e:
            answer += f"\n\n⚠️ 오류가 발생했습니다: {e}"
        status.empty()
        placeholder.markdown(answer or "_(빈 응답)_")

    history.append({"role": "assistant", "content": answer or "_(빈 응답)_", "steps": steps, "tool_log": tool_log,
                    "sent": sent_preview, "sent_count": sent_count})
    st.rerun()   # 노란 표시를 '다음 요청 기준'으로 다시 그린다
