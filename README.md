# LLM Only vs Agent 비교 채팅 (수업용)

Streamlit + Anthropic Python SDK. 같은 모델로 '그냥 언어모델'과 '에이전트'를 나란히 비교한다.

| 모드 | 이전 대화 | 오늘 날짜 | 웹검색 | 파일첨부 |
|---|---|---|---|---|
| LLM Only | ✗ (이번 질문만 보냄) | ✗ | ✗ | ✓ (이미지·PDF 읽기는 모델 자체 기능) |
| Agent | 토글 · 최근 N턴 | 토글 (`get_current_datetime` 도구) | 토글 (Anthropic 웹검색) | ✓ (이미지·PDF·텍스트, 10MB) |

- 모델: 앱 구동 시 Models API 로 계열별 최신을 조회. **Haiku 만 활성**(`ENABLED_FAMILIES`), 나머지는 드롭다운에 보이되 회색·선택 불가
- Chat History 를 켜면 **다음 요청에 함께 보내지는 메시지가 노란색**으로 표시된다
- 답변마다 `이 답변을 위해 보낸 messages` · `에이전트 동작(도구 호출·검색 출처)` 펼쳐 보기

## 로컬 실행
```
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # 키 입력
streamlit run app.py
```

## Streamlit Cloud 배포
1. 이 폴더를 GitHub 저장소로 올린다 (`secrets.toml` 은 .gitignore 로 제외됨)
2. share.streamlit.io → New app → 저장소·`app.py` 선택
3. Advanced settings → Secrets 에 `secrets.toml.example` 형식으로 키 입력 (`sk-ant-usr…` 키면 `ANTHROPIC_WORKSPACE_ID` 필수)
