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

MOCK_CONSULTATION_SUMMARY = """환자 백승주(29세, 남성)는 어제부터 왼쪽 눈이 따가운 증상을 호소하고 있으며, 특히 눈을 뜨고 있을 때 증상이 더 심하다고 합니다. 환자는 눈물 흘림과 눈의 붉어짐을 추가 증상으로 보고하였습니다. 과거 안과 질병이나 전신 질환(당뇨병, 고혈압, 심장질환 등)은 없으며, 최근에 눈에 손상을 입거나 콘택트렌즈를 착용한 적도 없습니다. 인공눈물이나 다른 안약을 사용하지 않고 있으며, 증상이 발생하기 전에 특별한 활동이나 외상, 환경 변화도 없었다고 합니다. 환자는 눈을 오래 뜨고 있을 때 눈물이 나며, 눈의 붉어짐은 왼쪽 눈에만 약간 나타난다고 합니다. 눈을 감고 있을 때는 증상이 완화되며, 눈의 분비물은 없고 투명한 눈물만 흐른다고 합니다. 눈의 가려움증은 없습니다.""".strip()

MOCK_MID_TERM_DIAGNOSIS_SUMMARY = """### 전문가 소견 종합

**예상 질병**: 
- **건성안 증후군**: 모든 전문의가 건성안 증후군의 가능성을 높게 평가하였습니다. 환자가 눈을 오래 뜨고 있을 때 눈물이 나고, 눈을 감고 있을 때 증상이 완화되는 점은 건성안 증후군의 전형적인 증상입니다. 이는 눈물막의 불안정성이나 부족으로 인해 발생할 수 있으며, 눈물의 과도한 분비는 눈의 건조함을 보상하기 위한 반응일 수 있습니다.
- **각막염**: Expert1은 각막염의 가능성을 제시하였으나, 눈을 감고 있을 때 증상이 완화되는 점에서 건성안 증후군의 가능성을 더 높게 평가하였습니다.
- **결막염**: Expert3은 경미한 결막염의 가능성을 배제할 수 없다고 하였으나, 일반적인 결막염의 증상인 가려움증과 분비물이 없고, 눈의 붉어짐이 왼쪽 눈에만 약간 나타난다는 점에서 가능성이 낮다고 평가하였습니다.

**진단 근거**:
- **건성안 증후군**: 눈을 오래 뜨고 있을 때 증상이 심해지고, 눈을 감고 있을 때 완화되는 점은 건성안 증후군의 전형적인 증상입니다. 눈물막의 불안정성으로 인해 눈물 증발이 증가하여 눈물이 흐르거나 따가운 증상을 유발할 수 있습니다.
- **각막염 및 결막염**: 각막염의 경우 눈의 붉어짐과 따가움이 있을 수 있지만, 결막염의 경우 일반적으로 눈의 가려움증과 분비물이 동반됩니다. 환자는 이러한 증상을 보고하지 않았으며, 이는 결막염의 가능성을 낮춥니다.

### 추가 정보 요청 사항
- **환자에게 즉시 물어볼 질문**: 현재 추가로 물어볼 질문은 없습니다.
- **임상검사 권고 사항**: 추후 안과 방문 시 세극등 검사와 플루오레신 염색검사를 통해 정확한 진단이 필요합니다. 이는 건성안 증후군의 중증도와 각막 손상 여부를 판단하는 데 필수적입니다.
""".strip()


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
