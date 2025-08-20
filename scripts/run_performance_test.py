#!/usr/bin/env python3
"""
Performance testing script for HUB Connect API
Compares sync vs async implementation performance
"""

import asyncio
import subprocess
import time
import sys
import os
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

async def check_server_health(base_url: str = "http://localhost:8001") -> bool:
    """Check if the server is running and healthy"""
    import httpx
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{base_url}/")
            return response.status_code == 200
    except Exception:
        return False

def start_server():
    """Start the FastAPI server"""
    print("Starting HUB Connect API server...")
    process = subprocess.Popen([
        sys.executable, "run.py"
    ], cwd=project_root)
    
    # Wait for server to start
    time.sleep(5)
    return process

async def run_performance_tests():
    """Run comprehensive performance tests"""
    from benchmarks.performance_benchmark import run_benchmark
    
    print("Starting performance benchmark...")
    results = await run_benchmark()
    return results

async def main():
    """Main function to orchestrate performance testing"""
    print("HUB Connect API Performance Testing")
    print("="*50)
    
    # Check if server is already running
    is_running = await check_server_health()
    server_process = None
    
    if not is_running:
        print("Server not detected, starting server...")
        server_process = start_server()
        
        # Wait for server to be fully ready
        for i in range(30):  # Wait up to 30 seconds
            await asyncio.sleep(1)
            if await check_server_health():
                print("Server is ready!")
                break
            print(f"Waiting for server... ({i+1}/30)")
        else:
            print("ERROR: Server failed to start within 30 seconds")
            if server_process:
                server_process.terminate()
            return 1
    else:
        print("Server is already running, proceeding with tests...")
    
    try:
        # Run performance tests
        results = await run_performance_tests()
        
        print("\nPerformance testing completed successfully!")
        print(f"Results saved to: {project_root}/benchmarks/")
        
        # Print quick summary
        if results:
            avg_response_time = sum(r['avg_response_time'] for r in results) / len(results)
            avg_throughput = sum(r['requests_per_second'] for r in results) / len(results)
            success_rates = [r['success_rate'] for r in results]
            min_success_rate = min(success_rates)
            
            print(f"\nQuick Summary:")
            print(f"  Average Response Time: {avg_response_time:.3f}s")
            print(f"  Average Throughput: {avg_throughput:.1f} req/s")
            print(f"  Minimum Success Rate: {min_success_rate:.1f}%")
        
        return 0
        
    except Exception as e:
        print(f"ERROR: Performance testing failed: {str(e)}")
        return 1
        
    finally:
        # Clean up server if we started it
        if server_process:
            print("Shutting down server...")
            server_process.terminate()
            server_process.wait()

if __name__ == "__main__":
    # Ensure benchmarks directory exists
    benchmarks_dir = project_root / "benchmarks"
    benchmarks_dir.mkdir(exist_ok=True)
    
    # Run the performance tests
    exit_code = asyncio.run(main())
    sys.exit(exit_code)