import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app", 
        host="0.0.0.0", 
        port=8001, 
        reload=True,
        workers=4,  # Run with multiple processes
        timeout_keep_alive=5,  # Keep-alive timeout
        timeout_graceful_shutdown=30  # Graceful shutdown timeout
    )