import asyncio
import time
import statistics
import httpx
import matplotlib.pyplot as plt
import pandas as pd
from typing import List, Dict, Any
from contextlib import asynccontextmanager
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PerformanceBenchmark:
    """Performance benchmark for comparing sync vs async implementations"""
    
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self.results = []
        
    async def benchmark_endpoint(self, endpoint: str, params: Dict = None, 
                                concurrent_requests: int = 10, total_requests: int = 100) -> Dict[str, Any]:
        """Benchmark a specific endpoint with concurrent requests"""
        
        async def make_request(client: httpx.AsyncClient, request_id: int):
            start_time = time.time()
            try:
                response = await client.get(f"{self.base_url}{endpoint}", params=params)
                end_time = time.time()
                return {
                    "request_id": request_id,
                    "status_code": response.status_code,
                    "response_time": end_time - start_time,
                    "success": response.status_code == 200
                }
            except Exception as e:
                end_time = time.time()
                return {
                    "request_id": request_id,
                    "status_code": 0,
                    "response_time": end_time - start_time,
                    "success": False,
                    "error": str(e)
                }
        
        # Run benchmark
        start_time = time.time()
        results = []
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Process requests in batches to control concurrency
            for batch_start in range(0, total_requests, concurrent_requests):
                batch_end = min(batch_start + concurrent_requests, total_requests)
                batch_tasks = [
                    make_request(client, i) 
                    for i in range(batch_start, batch_end)
                ]
                
                batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
                results.extend([r for r in batch_results if not isinstance(r, Exception)])
        
        end_time = time.time()
        
        # Calculate statistics
        response_times = [r["response_time"] for r in results]
        successful_requests = [r for r in results if r["success"]]
        
        benchmark_result = {
            "endpoint": endpoint,
            "params": params,
            "total_requests": total_requests,
            "concurrent_requests": concurrent_requests,
            "total_time": end_time - start_time,
            "successful_requests": len(successful_requests),
            "failed_requests": len(results) - len(successful_requests),
            "success_rate": len(successful_requests) / len(results) * 100,
            "avg_response_time": statistics.mean(response_times) if response_times else 0,
            "min_response_time": min(response_times) if response_times else 0,
            "max_response_time": max(response_times) if response_times else 0,
            "median_response_time": statistics.median(response_times) if response_times else 0,
            "p95_response_time": self._percentile(response_times, 95) if response_times else 0,
            "p99_response_time": self._percentile(response_times, 99) if response_times else 0,
            "requests_per_second": len(successful_requests) / (end_time - start_time),
            "errors": [r.get("error") for r in results if not r["success"]]
        }
        
        self.results.append(benchmark_result)
        return benchmark_result
    
    def _percentile(self, data: List[float], percentile: int) -> float:
        """Calculate percentile of data"""
        sorted_data = sorted(data)
        index = (percentile / 100) * (len(sorted_data) - 1)
        if index.is_integer():
            return sorted_data[int(index)]
        else:
            lower = sorted_data[int(index)]
            upper = sorted_data[int(index) + 1]
            return lower + (upper - lower) * (index - int(index))
    
    async def run_comprehensive_benchmark(self):
        """Run comprehensive benchmark on all major endpoints"""
        logger.info("Starting comprehensive performance benchmark...")
        
        # Test scenarios
        scenarios = [
            {
                "name": "Trending Models",
                "endpoint": "/api/v1/models",
                "params": {"sort": "trending", "page": 1},
                "concurrent": [1, 5, 10, 20],
                "total_requests": 50
            },
            {
                "name": "Search Models",
                "endpoint": "/api/v1/models", 
                "params": {"query": "bert", "sort": "downloads", "page": 1},
                "concurrent": [1, 5, 10, 20],
                "total_requests": 50
            },
            {
                "name": "Model Files",
                "endpoint": "/api/v1/models/bert-base-uncased/files",
                "params": {},
                "concurrent": [1, 5, 10],
                "total_requests": 30
            },
            {
                "name": "Storage List",
                "endpoint": "/api/v1/storage",
                "params": {},
                "concurrent": [1, 5, 10, 20],
                "total_requests": 50
            }
        ]
        
        all_results = []
        
        for scenario in scenarios:
            logger.info(f"Benchmarking: {scenario['name']}")
            
            for concurrent in scenario["concurrent"]:
                logger.info(f"  Testing with {concurrent} concurrent requests...")
                
                result = await self.benchmark_endpoint(
                    endpoint=scenario["endpoint"],
                    params=scenario["params"],
                    concurrent_requests=concurrent,
                    total_requests=scenario["total_requests"]
                )
                
                result["scenario"] = scenario["name"]
                all_results.append(result)
                
                logger.info(f"    Success Rate: {result['success_rate']:.1f}%")
                logger.info(f"    Avg Response Time: {result['avg_response_time']:.3f}s")
                logger.info(f"    Requests/sec: {result['requests_per_second']:.1f}")
                logger.info(f"    P95 Response Time: {result['p95_response_time']:.3f}s")
                
                # Brief pause between tests
                await asyncio.sleep(1)
        
        return all_results
    
    def generate_performance_report(self, results: List[Dict[str, Any]]) -> pd.DataFrame:
        """Generate performance report as DataFrame"""
        df = pd.DataFrame(results)
        
        # Select key metrics for the report
        report_columns = [
            'scenario', 'concurrent_requests', 'total_requests',
            'success_rate', 'avg_response_time', 'p95_response_time', 
            'p99_response_time', 'requests_per_second'
        ]
        
        report_df = df[report_columns].copy()
        
        # Round numeric columns for better readability
        numeric_columns = ['success_rate', 'avg_response_time', 'p95_response_time', 
                          'p99_response_time', 'requests_per_second']
        for col in numeric_columns:
            report_df[col] = report_df[col].round(3)
        
        return report_df
    
    def create_performance_charts(self, results: List[Dict[str, Any]], output_dir: str = "benchmarks"):
        """Create performance visualization charts"""
        import os
        
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        df = pd.DataFrame(results)
        
        # 1. Response Time vs Concurrency by Scenario
        plt.figure(figsize=(12, 8))
        scenarios = df['scenario'].unique()
        
        for scenario in scenarios:
            scenario_data = df[df['scenario'] == scenario]
            plt.plot(scenario_data['concurrent_requests'], 
                    scenario_data['avg_response_time'],
                    marker='o', label=scenario)
        
        plt.xlabel('Concurrent Requests')
        plt.ylabel('Average Response Time (seconds)')
        plt.title('Response Time vs Concurrency by Scenario')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.savefig(f"{output_dir}/response_time_vs_concurrency.png", dpi=300, bbox_inches='tight')
        plt.close()
        
        # 2. Requests per Second vs Concurrency
        plt.figure(figsize=(12, 8))
        
        for scenario in scenarios:
            scenario_data = df[df['scenario'] == scenario]
            plt.plot(scenario_data['concurrent_requests'],
                    scenario_data['requests_per_second'],
                    marker='o', label=scenario)
        
        plt.xlabel('Concurrent Requests')
        plt.ylabel('Requests per Second')
        plt.title('Throughput vs Concurrency by Scenario')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.savefig(f"{output_dir}/throughput_vs_concurrency.png", dpi=300, bbox_inches='tight')
        plt.close()
        
        # 3. Success Rate vs Concurrency
        plt.figure(figsize=(12, 8))
        
        for scenario in scenarios:
            scenario_data = df[df['scenario'] == scenario]
            plt.plot(scenario_data['concurrent_requests'],
                    scenario_data['success_rate'],
                    marker='o', label=scenario)
        
        plt.xlabel('Concurrent Requests')
        plt.ylabel('Success Rate (%)')
        plt.title('Success Rate vs Concurrency by Scenario')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.ylim(90, 102)  # Focus on the important range
        plt.savefig(f"{output_dir}/success_rate_vs_concurrency.png", dpi=300, bbox_inches='tight')
        plt.close()
        
        # 4. P95 vs P99 Response Times
        plt.figure(figsize=(12, 8))
        
        x_pos = range(len(df))
        width = 0.35
        
        plt.bar([x - width/2 for x in x_pos], df['p95_response_time'], 
                width, label='P95', alpha=0.8)
        plt.bar([x + width/2 for x in x_pos], df['p99_response_time'], 
                width, label='P99', alpha=0.8)
        
        plt.xlabel('Test Cases')
        plt.ylabel('Response Time (seconds)')
        plt.title('P95 vs P99 Response Times')
        plt.legend()
        plt.xticks(x_pos, [f"{row['scenario']}\n({row['concurrent_requests']} concurrent)" 
                          for _, row in df.iterrows()], rotation=45, ha='right')
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(f"{output_dir}/percentile_response_times.png", dpi=300, bbox_inches='tight')
        plt.close()
        
        logger.info(f"Performance charts saved to {output_dir}/")

async def run_benchmark():
    """Main function to run the benchmark"""
    benchmark = PerformanceBenchmark()
    
    # Run comprehensive benchmark
    results = await benchmark.run_comprehensive_benchmark()
    
    # Generate report
    report_df = benchmark.generate_performance_report(results)
    
    # Save results to CSV
    report_df.to_csv("benchmarks/performance_report.csv", index=False)
    
    # Create visualization charts
    benchmark.create_performance_charts(results)
    
    # Print summary
    print("\n" + "="*80)
    print("PERFORMANCE BENCHMARK SUMMARY")
    print("="*80)
    print(report_df.to_string(index=False))
    print("\n")
    
    # Overall statistics
    print("OVERALL STATISTICS:")
    print(f"Total test scenarios: {len(report_df['scenario'].unique())}")
    print(f"Average success rate: {report_df['success_rate'].mean():.1f}%")
    print(f"Average response time: {report_df['avg_response_time'].mean():.3f}s")
    print(f"Average throughput: {report_df['requests_per_second'].mean():.1f} req/s")
    print(f"Best throughput: {report_df['requests_per_second'].max():.1f} req/s")
    print(f"Worst P99 response time: {report_df['p99_response_time'].max():.3f}s")
    
    return results

if __name__ == "__main__":
    # Run the benchmark
    asyncio.run(run_benchmark())