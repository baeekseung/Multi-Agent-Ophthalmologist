#!/usr/bin/env python3
"""
diagnosis_agent_node 단독 테스트 스크립트

전체 그래프(상담 + 중간분석 단계)를 거치지 않고
diagnosis_agent_node를 mock 데이터로 직접 실행하여 동작을 검증합니다.

실행 방법:
    conda activate AgenticOphtimusEnv && python test_diagnosis_agent.py

로그 확인:
    grep "[TASK]" logs/test_diagnosis_*.log
"""

import asyncio
from datetime import datetime
from dotenv import load_dotenv

# 1번: 환경변수 로드 (OPENAI_API_KEY, TAVILY_API_KEY 등)
load_dotenv()

# 2번: 로깅 설정 (app 모듈 import 전에 반드시 호출)
from app.utils.logger import setup_logging, get_logger

thread_id = f"test_diagnosis_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
setup_logging(thread_id)
logger = get_logger(__name__)

# ──────────────────────────────────────────────────────────
# Mock 데이터: 백승주, 29세 남성, 왼쪽 눈 따가움
# ──────────────────────────────────────────────────────────

MOCK_CONSULTATION_SUMMARY = """환자 백승주님은 41세 남성으로, 최근 한두 달 전부터 글자가 휘어 보이고, 특히 책이나 휴대폰을 볼 때 가운데 부분이 일그러져 보이는 증상을 경험하고 있습니다. 정면을 보면 중심이 또렷하지 않고 흐릿한 느낌도 있다고 합니다. 증상은 두 달 전쯤 시작되었으며, 처음에는 피곤해서 그런 줄 알았으나 점점 더 느껴지기 시작했습니다. 과거에 특별한 안과 질환을 진단받은 적은 없으며, 안경을 오래전부터 사용하고 있습니다. 전신 질환으로는 당뇨나 심장질환은 없고, 혈압이 조금 높다는 이야기를 들은 적이 있으나 약을 복용할 정도는 아니라고 합니다. 증상은 양쪽 눈에 모두 나타나지만, 오른쪽 눈이 더 심하게 느껴진다고 합니다. 시력이 예전보다 떨어진 느낌이 있으며, 특히 가까운 글자를 볼 때 선명하지 않고 초점이 맞지 않는다고 합니다. 스트레스는 없으나 책이나 휴대폰을 오래 보면 증상이 더 뚜렷하게 느껴지며, 밝은 곳에서 글자를 보면 가운데 부분이 비어 보이는 느낌도 있다고 합니다. 가족력으로는 아버지가 망막 쪽이 안 좋다는 이야기를 들은 적이 있습니다. 최근에 새로운 약물 복용이나 생활 습관의 변화는 없으며, 하루에 반갑 정도의 흡연을 20년간 해왔고, 주말에 한두 번 소주 한 병 정도의 음주를 하고 있습니다.""".strip()

MOCK_MID_TERM_DIAGNOSIS_SUMMARY = """### 전문가 소견 종합

**예상 질병**: 
1. **황반변성 (Age-related Macular Degeneration, AMD)**
2. **중심장액맥락망막병증 (Central Serous Chorioretinopathy, CSC)**

**진단 근거**:
- **황반변성**: 환자는 양쪽 눈에 증상이 나타나지만 오른쪽 눈이 더 심하고, 시력이 떨어진 느낌이 있습니다. 특히 가까운 글자를 볼 때 선명하지 않고 초점이 맞지 않는다는 점은 황반변성의 전형적인 증상과 일치합니다. 가족력으로 아버지가 망막 질환을 앓았다는 점도 황반변성의 가능성을 높입니다. 흡연 습관 역시 황반변성의 위험 요인 중 하나입니다.
- **중심장액맥락망막병증**: 환자가 스트레스는 없다고 하지만, 책이나 휴대폰을 오래 보면 증상이 더 뚜렷하게 느껴진다는 점에서 중심장액맥락망막병증의 가능성도 고려됩니다. 이 질환은 주로 젊은 남성에게 발생하며, 환자의 흡연 습관도 위험 요인으로 작용할 수 있습니다.

### 추가 정보 요청 사항
- 현재 추가로 물어볼 정보는 없습니다. 모든 전문의가 추가 정보 없이도 진단 방향을 설정할 수 있다고 판단하였습니다.

### 임상검사 권고 사항
- 추후 안과 방문 시 **플루오레신 안저 촬영검사** 및 **광각 망막 검사**를 권고합니다. 이는 황반변성과 중심장액맥락망막병증의 확진에 필요합니다.""".strip()


async def main():
    # 3번: app 모듈 동적 import (setup_logging 호출 이후)
    from app.node.diagnosis_agent import diagnosis_agent_node
    from langgraph.graph import END

    # Mock state 구성 (state.get() 패턴 사용으로 일반 dict 충분)
    mock_state = {
        "messages": [],
        "supervisor_messages": [],
        "expert1_messages": [],
        "expert2_messages": [],
        "expert3_messages": [],
        "consultation_summary": MOCK_CONSULTATION_SUMMARY,
        "mid_term_diagnosis_summary": MOCK_MID_TERM_DIAGNOSIS_SUMMARY,
    }

    logger.info(f"[TEST] diagnosis_agent_node 테스트 시작 | thread_id: {thread_id}")
    logger.info(f"[TEST] 환자: 백승주 29세 남성 | 주호소: 왼쪽 눈 따가움")

    # diagnosis_agent_node 실행
    result_command = await diagnosis_agent_node(mock_state)

    # ── 결과 추출 ──────────────────────────────────────────
    result_update = result_command.update
    final_report = result_update.get("diagnosis_research_result", "")

    # ── 검증 ───────────────────────────────────────────────
    print("\n" + "="*60)
    print("검증 결과")
    print("="*60)

    # 검증 1: diagnosis_research_result 키 존재 여부
    check1 = "diagnosis_research_result" in result_update
    print(f"{'[PASS]' if check1 else '[FAIL]'} diagnosis_research_result 키 존재")
    assert check1, "diagnosis_research_result 키가 없습니다"

    # 검증 2: 결과 길이 100자 이상
    check2 = len(final_report) >= 100
    print(f"{'[PASS]' if check2 else '[FAIL]'} 결과 길이 충분: {len(final_report)}자")
    assert check2, f"결과가 너무 짧습니다: {len(final_report)}자"

    # 검증 3: goto == END
    check3 = result_command.goto == END
    print(f"{'[PASS]' if check3 else '[FAIL]'} goto == END ({result_command.goto!r})")
    assert check3, f"goto가 END가 아닙니다: {result_command.goto!r}"

    # ── 보고서 출력 ────────────────────────────────────────
    print("\n" + "="*60)
    print("최종 진단 연구 보고서")
    print("="*60)
    print(final_report)

    print("\n" + "="*60)
    print(f"[TEST] 완료 | 로그 파일: logs/{thread_id}.log")
    print("="*60)

    logger.info(f"[TEST] 모든 검증 통과 | 보고서 길이: {len(final_report)}자")


if __name__ == "__main__":
    asyncio.run(main())
