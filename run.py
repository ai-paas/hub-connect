import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app", 
        host="0.0.0.0", 
        port=8001, 
        reload=True,
        workers=4,  # 멀티 프로세스로 실행
        timeout_keep_alive=5,  # Keep-alive 타임아웃
        timeout_graceful_shutdown=30  # Graceful shutdown 타임아웃
    )