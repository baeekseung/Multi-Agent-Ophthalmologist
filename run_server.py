import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",     # "모듈경로:FastAPI앱변수명"
        host="0.0.0.0",     # 모든 네트워크 인터페이스에서 수신 (127.0.0.1이면 로컬만)
        port=8000,
        reload=True,        # 코드 변경 시 자동 재시작 (개발 환경용)
    )
