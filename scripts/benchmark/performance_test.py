#!/usr/bin/env python3
"""
Script de benchmark pour tester les performances de l'API RDTM
"""

import asyncio
import time
import statistics
from typing import List
import httpx


async def benchmark_endpoint(
    url: str, 
    concurrent_requests: int = 10, 
    total_requests: int = 100
) -> dict:
    """Benchmark d'un endpoint spécifique"""
    
    async def single_request(client: httpx.AsyncClient) -> float:
        start_time = time.time()
        try:
            response = await client.get(url)
            response.raise_for_status()
            return time.time() - start_time
        except Exception as e:
            print(f"Erreur lors de la requête: {e}")
            return -1

    async with httpx.AsyncClient() as client:
        tasks = []
        response_times = []
        
        # Exécution des requêtes par batch
        for i in range(0, total_requests, concurrent_requests):
            batch_size = min(concurrent_requests, total_requests - i)
            batch_tasks = [single_request(client) for _ in range(batch_size)]
            
            batch_results = await asyncio.gather(*batch_tasks)
            response_times.extend([rt for rt in batch_results if rt > 0])
            
            # Pause entre les batches
            await asyncio.sleep(0.1)
    
    if not response_times:
        return {"error": "Aucune requête réussie"}
    
    return {
        "total_requests": len(response_times),
        "avg_response_time": statistics.mean(response_times),
        "median_response_time": statistics.median(response_times),
        "min_response_time": min(response_times),
        "max_response_time": max(response_times),
        "p95_response_time": statistics.quantiles(response_times, n=20)[18],
        "p99_response_time": statistics.quantiles(response_times, n=100)[98],
    }


async def main():
    """Fonction principale de benchmark"""
    base_url = "http://localhost:8000"
    
    endpoints = [
        "/health",
        "/api/v1/torrents",
        "/api/v1/downloads",
    ]
    
    print("🚀 Début du benchmark RDTM")
    print("=" * 50)
    
    for endpoint in endpoints:
        print(f"\n📊 Test de {endpoint}")
        results = await benchmark_endpoint(f"{base_url}{endpoint}")
        
        if "error" in results:
            print(f"❌ {results['error']}")
            continue
            
        print(f"✅ Requêtes réussies: {results['total_requests']}")
        print(f"⏱️  Temps moyen: {results['avg_response_time']:.3f}s")
        print(f"📈 P95: {results['p95_response_time']:.3f}s")
        print(f"📈 P99: {results['p99_response_time']:.3f}s")


if __name__ == "__main__":
    asyncio.run(main())
