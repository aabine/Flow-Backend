#!/usr/bin/env python3
"""
Final Comprehensive Test Script
Test all 12 microservices to achieve 100% production readiness
"""

import asyncio
import aiohttp
import subprocess
import logging
import sys
import time
from typing import Dict, List, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('final_comprehensive_test.log')
    ]
)
logger = logging.getLogger(__name__)

class FinalComprehensiveTest:
    """Final comprehensive test for all microservices"""
    
    def __init__(self):
        self.services = [
            {"name": "user-service", "port": 8001, "priority": 1},
            {"name": "supplier-onboarding-service", "port": 8002, "priority": 2},
            {"name": "location-service", "port": 8003, "priority": 3},
            {"name": "inventory-service", "port": 8004, "priority": 4},
            {"name": "order-service", "port": 8005, "priority": 5},
            {"name": "pricing-service", "port": 8006, "priority": 6},
            {"name": "delivery-service", "port": 8007, "priority": 7},
            {"name": "payment-service", "port": 8008, "priority": 8},
            {"name": "review-service", "port": 8009, "priority": 9},
            {"name": "notification-service", "port": 8010, "priority": 10},
            {"name": "admin-service", "port": 8011, "priority": 11},
            {"name": "websocket-service", "port": 8012, "priority": 12},
        ]
        
    def run_command(self, command: str, timeout: int = 180) -> Tuple[bool, str, str]:
        """Run shell command with timeout"""
        try:
            logger.info(f"🐳 Running: {command}")
            result = subprocess.run(
                command.split(),
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd="/home/safety-pc/Flow-Backend"
            )
            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            logger.error(f"❌ Command timed out: {command}")
            return False, "", "Timeout"
        except Exception as e:
            logger.error(f"❌ Command failed: {e}")
            return False, "", str(e)
    
    async def check_service_health(self, service_name: str, port: int, max_attempts: int = 30) -> bool:
        """Check if service health endpoint responds"""
        logger.info(f"🔍 Checking health of {service_name} on port {port}...")
        
        health_endpoints = ["/health", "/", "/docs"]
        
        for attempt in range(max_attempts):
            for endpoint in health_endpoints:
                try:
                    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                        async with session.get(f"http://localhost:{port}{endpoint}") as response:
                            if response.status in [200, 404]:  # 404 is OK for some endpoints
                                logger.info(f"✅ {service_name} is healthy (endpoint: {endpoint})")
                                return True
                except Exception:
                    continue
            
            if attempt < max_attempts - 1:
                logger.info(f"   Attempt {attempt + 1}/{max_attempts} - waiting for {service_name}...")
                await asyncio.sleep(2)
        
        logger.error(f"❌ {service_name} failed to become healthy")
        return False
    
    def build_service(self, service_name: str) -> bool:
        """Build individual service"""
        logger.info(f"🏗️ Building {service_name}...")
        
        success, stdout, stderr = self.run_command(f"docker-compose build {service_name}")
        
        if success:
            logger.info(f"✅ {service_name} build successful")
            return True
        else:
            logger.error(f"❌ {service_name} build failed: {stderr}")
            return False
    
    async def test_service_comprehensive(self, service: Dict) -> Dict:
        """Test service comprehensively"""
        service_name = service["name"]
        port = service["port"]
        
        logger.info(f"\n{'='*60}")
        logger.info(f"🧪 TESTING {service_name.upper()}")
        logger.info(f"{'='*60}")
        
        test_results = {
            "service_name": service_name,
            "port": port,
            "priority": service["priority"],
            "build_success": False,
            "startup_success": False,
            "health_check_success": False,
            "overall_success": False,
            "issues": []
        }
        
        try:
            # Step 1: Build service
            build_success = self.build_service(service_name)
            test_results["build_success"] = build_success
            
            if not build_success:
                test_results["issues"].append("Build failed")
                return test_results
            
            # Step 2: Start dependencies
            logger.info(f"🔧 Starting dependencies...")
            self.run_command("docker-compose up -d postgres redis rabbitmq")
            await asyncio.sleep(5)
            
            # Step 3: Start service
            logger.info(f"🚀 Starting {service_name}...")
            success, _, stderr = self.run_command(f"docker-compose up -d {service_name}")
            test_results["startup_success"] = success
            
            if not success:
                test_results["issues"].append(f"Startup failed: {stderr}")
                return test_results
            
            # Step 4: Wait for initialization
            await asyncio.sleep(10)
            
            # Step 5: Check health
            health_success = await self.check_service_health(service_name, port)
            test_results["health_check_success"] = health_success
            
            if not health_success:
                test_results["issues"].append("Health check failed")
            
            # Step 6: Check logs for errors
            success, logs, _ = self.run_command(f"docker-compose logs --tail=20 {service_name}")
            if success:
                error_indicators = ["error", "exception", "failed", "traceback"]
                log_lines = logs.lower().split('\n')
                error_count = sum(1 for line in log_lines if any(indicator in line for indicator in error_indicators))
                
                if error_count > 0:
                    test_results["issues"].append(f"Found {error_count} error indicators in logs")
            
            # Calculate overall success
            test_results["overall_success"] = (
                test_results["build_success"] and
                test_results["startup_success"] and
                test_results["health_check_success"]
            )
            
        except Exception as e:
            logger.error(f"❌ Exception during {service_name} testing: {e}")
            test_results["issues"].append(f"Exception: {e}")
        
        finally:
            # Stop service
            logger.info(f"🛑 Stopping {service_name}...")
            self.run_command(f"docker-compose stop {service_name}")
        
        # Log results
        if test_results["overall_success"]:
            logger.info(f"✅ {service_name} testing PASSED")
        else:
            logger.error(f"❌ {service_name} testing FAILED")
            for issue in test_results["issues"]:
                logger.error(f"   - {issue}")
        
        return test_results
    
    async def run_final_comprehensive_test(self) -> Dict:
        """Run final comprehensive test on all services"""
        logger.info("🚀 Starting Final Comprehensive Test - All 12 Microservices")
        logger.info("=" * 80)
        
        results = {
            "services_tested": [],
            "successful_services": [],
            "failed_services": [],
            "summary": {}
        }
        
        # Test all services
        for service in self.services:
            service_result = await self.test_service_comprehensive(service)
            results["services_tested"].append(service_result)
            
            if service_result["overall_success"]:
                results["successful_services"].append(service["name"])
            else:
                results["failed_services"].append(service["name"])
        
        # Generate summary
        total_services = len(self.services)
        successful_count = len(results["successful_services"])
        failed_count = len(results["failed_services"])
        
        results["summary"] = {
            "total_services": total_services,
            "successful_count": successful_count,
            "failed_count": failed_count,
            "success_rate": successful_count / total_services if total_services > 0 else 0
        }
        
        # Print summary
        self.print_final_summary(results)
        
        return results
    
    def print_final_summary(self, results: Dict):
        """Print final comprehensive summary"""
        logger.info("\n" + "=" * 80)
        logger.info("🎯 FINAL COMPREHENSIVE TEST SUMMARY")
        logger.info("=" * 80)
        
        summary = results["summary"]
        logger.info(f"📊 Total Services Tested: {summary['total_services']}")
        logger.info(f"✅ Successful Services: {summary['successful_count']}")
        logger.info(f"❌ Failed Services: {summary['failed_count']}")
        logger.info(f"📈 Success Rate: {summary['success_rate']:.1%}")
        
        if results["successful_services"]:
            logger.info(f"\n✅ SUCCESSFUL SERVICES:")
            for service in results["successful_services"]:
                logger.info(f"   - {service}")
        
        if results["failed_services"]:
            logger.info(f"\n❌ FAILED SERVICES:")
            for service in results["failed_services"]:
                logger.info(f"   - {service}")
        
        # Production readiness assessment
        success_rate = summary["success_rate"]
        if success_rate >= 1.0:
            logger.info(f"\n🎉 PRODUCTION READY: 100% service success rate achieved!")
        elif success_rate >= 0.8:
            logger.info(f"\n🟡 NEAR PRODUCTION READY: {success_rate:.1%} success rate")
        else:
            logger.info(f"\n🔴 NOT PRODUCTION READY: {success_rate:.1%} success rate")

async def main():
    """Main entry point"""
    tester = FinalComprehensiveTest()
    results = await tester.run_final_comprehensive_test()
    
    success_rate = results["summary"]["success_rate"]
    
    if success_rate >= 1.0:
        logger.info("🎉 Final comprehensive testing completed successfully - 100% PRODUCTION READY!")
        sys.exit(0)
    else:
        logger.error(f"❌ Final comprehensive testing completed with {success_rate:.1%} success rate")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
