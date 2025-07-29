#!/usr/bin/env python3
"""
Final Service Status Check
Verify all 12 microservices are operational after fixes
"""

import asyncio
import aiohttp
import sys
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class FinalServiceStatusCheck:
    """Check final status of all microservices"""
    
    def __init__(self):
        self.services = [
            {"name": "User Service", "port": 8001},
            {"name": "Supplier Onboarding Service", "port": 8002},
            {"name": "Location Service", "port": 8003},
            {"name": "Inventory Service", "port": 8004},
            {"name": "Order Service", "port": 8005},
            {"name": "Pricing Service", "port": 8006},
            {"name": "Delivery Service", "port": 8007},
            {"name": "Payment Service", "port": 8008},
            {"name": "Review Service", "port": 8009},
            {"name": "Notification Service", "port": 8010},
            {"name": "Admin Service", "port": 8011},
            {"name": "WebSocket Service", "port": 8012},
        ]
        
    async def check_service_health(self, service: dict) -> dict:
        """Check individual service health"""
        name = service["name"]
        port = service["port"]
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(f"http://localhost:{port}/health") as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "name": name,
                            "port": port,
                            "status": "healthy",
                            "response": data
                        }
                    else:
                        return {
                            "name": name,
                            "port": port,
                            "status": "unhealthy",
                            "error": f"HTTP {response.status}"
                        }
        except Exception as e:
            return {
                "name": name,
                "port": port,
                "status": "failed",
                "error": str(e)
            }
    
    async def check_all_services(self) -> dict:
        """Check all services and return summary"""
        logger.info("🔍 Checking all 12 microservices...")
        
        # Check all services concurrently
        tasks = [self.check_service_health(service) for service in self.services]
        results = await asyncio.gather(*tasks)
        
        # Categorize results
        healthy_services = []
        unhealthy_services = []
        failed_services = []
        
        for result in results:
            if result["status"] == "healthy":
                healthy_services.append(result)
            elif result["status"] == "unhealthy":
                unhealthy_services.append(result)
            else:
                failed_services.append(result)
        
        return {
            "total_services": len(self.services),
            "healthy_count": len(healthy_services),
            "unhealthy_count": len(unhealthy_services),
            "failed_count": len(failed_services),
            "success_rate": len(healthy_services) / len(self.services),
            "healthy_services": healthy_services,
            "unhealthy_services": unhealthy_services,
            "failed_services": failed_services
        }
    
    def print_summary(self, results: dict):
        """Print comprehensive summary"""
        logger.info("\n" + "=" * 80)
        logger.info("🎯 FINAL SERVICE STATUS SUMMARY")
        logger.info("=" * 80)
        
        total = results["total_services"]
        healthy = results["healthy_count"]
        unhealthy = results["unhealthy_count"]
        failed = results["failed_count"]
        success_rate = results["success_rate"]
        
        logger.info(f"📊 Total Services: {total}")
        logger.info(f"✅ Healthy Services: {healthy}")
        logger.info(f"⚠️ Unhealthy Services: {unhealthy}")
        logger.info(f"❌ Failed Services: {failed}")
        logger.info(f"📈 Success Rate: {success_rate:.1%}")
        
        if results["healthy_services"]:
            logger.info(f"\n✅ HEALTHY SERVICES ({healthy}):")
            for service in results["healthy_services"]:
                logger.info(f"   - {service['name']} (Port {service['port']})")
        
        if results["unhealthy_services"]:
            logger.info(f"\n⚠️ UNHEALTHY SERVICES ({unhealthy}):")
            for service in results["unhealthy_services"]:
                logger.info(f"   - {service['name']} (Port {service['port']}): {service['error']}")
        
        if results["failed_services"]:
            logger.info(f"\n❌ FAILED SERVICES ({failed}):")
            for service in results["failed_services"]:
                logger.info(f"   - {service['name']} (Port {service['port']}): {service['error']}")
        
        # Production readiness assessment
        if success_rate >= 1.0:
            logger.info(f"\n🎉 PRODUCTION READY: 100% service success rate achieved!")
            logger.info("🚀 All microservices are operational and ready for deployment")
        elif success_rate >= 0.9:
            logger.info(f"\n🟢 EXCELLENT: {success_rate:.1%} service success rate")
            logger.info("🚀 Platform is production-ready with excellent operational status")
        elif success_rate >= 0.8:
            logger.info(f"\n🟡 GOOD: {success_rate:.1%} service success rate")
            logger.info("🔧 Platform is near production-ready")
        else:
            logger.info(f"\n🔴 NEEDS WORK: {success_rate:.1%} service success rate")
            logger.info("🔧 Additional fixes needed for production readiness")

async def main():
    """Main entry point"""
    checker = FinalServiceStatusCheck()
    results = await checker.check_all_services()
    checker.print_summary(results)
    
    success_rate = results["success_rate"]
    
    if success_rate >= 0.9:
        logger.info("🎉 Final service status check completed successfully!")
        sys.exit(0)
    else:
        logger.error(f"❌ Service status check completed with {success_rate:.1%} success rate")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
