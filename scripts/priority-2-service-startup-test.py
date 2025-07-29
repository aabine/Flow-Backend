#!/usr/bin/env python3
"""
Priority 2: Service Startup Testing Script
Tests each failing service individually to identify and fix startup issues
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
        logging.FileHandler('priority_2_startup_test.log')
    ]
)
logger = logging.getLogger(__name__)

class ServiceStartupTester:
    """Test individual service startup and identify issues"""
    
    def __init__(self):
        self.failing_services = [
            {"name": "location-service", "port": 8003},
            {"name": "supplier-onboarding-service", "port": 8002},
            {"name": "pricing-service", "port": 8006},
            {"name": "delivery-service", "port": 8007},
            {"name": "review-service", "port": 8009},
            {"name": "notification-service", "port": 8010},
            {"name": "admin-service", "port": 8011},
            {"name": "websocket-service", "port": 8012},
        ]
        
    def run_docker_command(self, command: str, timeout: int = 120) -> Tuple[bool, str]:
        """Run docker command and return success status and output"""
        try:
            logger.info(f"🐳 Running: {command}")
            result = subprocess.run(
                command.split(),
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd="/home/safety-pc/Flow-Backend"
            )
            
            if result.returncode == 0:
                return True, result.stdout
            else:
                logger.error(f"❌ Command failed: {result.stderr}")
                return False, result.stderr
                
        except subprocess.TimeoutExpired:
            logger.error(f"❌ Command timed out after {timeout} seconds")
            return False, "Command timed out"
        except Exception as e:
            logger.error(f"❌ Command error: {e}")
            return False, str(e)
    
    async def check_service_health(self, service_name: str, port: int, max_attempts: int = 60) -> bool:
        """Check if service health endpoint responds with extended timeout"""
        logger.info(f"🔍 Checking health of {service_name} on port {port} (extended timeout)...")
        
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
        
        logger.error(f"❌ {service_name} failed to become healthy after {max_attempts * 2} seconds")
        return False
    
    def check_build_logs(self, service_name: str) -> Tuple[bool, List[str]]:
        """Check Docker build logs for errors"""
        logger.info(f"🔍 Checking build logs for {service_name}...")
        
        success, output = self.run_docker_command(f"docker-compose build {service_name}")
        
        issues = []
        if not success:
            issues.append(f"Build failed: {output}")
            return False, issues
        
        # Check for common issues in build output
        build_issues = []
        if "ERROR" in output.upper():
            build_issues.append("Build errors detected")
        if "ModuleNotFoundError" in output:
            build_issues.append("Missing Python modules")
        if "jwt" in output.lower() and "error" in output.lower():
            build_issues.append("JWT dependency issues")
        if "timeout" in output.lower():
            build_issues.append("Build timeout issues")
        
        return True, build_issues
    
    def check_startup_logs(self, service_name: str) -> List[str]:
        """Check service startup logs for errors"""
        logger.info(f"📋 Checking startup logs for {service_name}...")
        
        success, logs = self.run_docker_command(f"docker-compose logs --tail=50 {service_name}")
        
        issues = []
        if success:
            log_lines = logs.split('\n')
            for line in log_lines:
                line_lower = line.lower()
                if any(error_term in line_lower for error_term in ['error', 'exception', 'failed', 'traceback']):
                    if 'jwt' in line_lower:
                        issues.append(f"JWT Error: {line.strip()}")
                    elif 'modulenotfounderror' in line_lower:
                        issues.append(f"Missing Module: {line.strip()}")
                    elif 'connection' in line_lower and 'failed' in line_lower:
                        issues.append(f"Connection Error: {line.strip()}")
                    else:
                        issues.append(f"General Error: {line.strip()}")
        
        return issues
    
    async def test_individual_service_startup(self, service: Dict) -> Dict:
        """Test individual service startup with detailed diagnostics"""
        service_name = service["name"]
        port = service["port"]
        
        logger.info(f"\n{'='*60}")
        logger.info(f"🧪 TESTING {service_name.upper()} STARTUP")
        logger.info(f"{'='*60}")
        
        test_results = {
            "service_name": service_name,
            "port": port,
            "build_success": False,
            "startup_success": False,
            "health_check_success": False,
            "issues": [],
            "recommendations": []
        }
        
        try:
            # Step 1: Stop service if running
            logger.info(f"🛑 Stopping {service_name} if running...")
            self.run_docker_command(f"docker-compose stop {service_name}")
            
            # Step 2: Check build
            build_success, build_issues = self.check_build_logs(service_name)
            test_results["build_success"] = build_success
            test_results["issues"].extend(build_issues)
            
            if not build_success:
                test_results["recommendations"].append("Fix Docker build issues before proceeding")
                return test_results
            
            # Step 3: Start dependencies
            logger.info(f"🔧 Ensuring dependencies are running...")
            self.run_docker_command("docker-compose up -d postgres redis rabbitmq")
            await asyncio.sleep(5)  # Give dependencies time to start
            
            # Step 4: Start the service
            logger.info(f"🚀 Starting {service_name}...")
            success, output = self.run_docker_command(f"docker-compose up -d {service_name}")
            test_results["startup_success"] = success
            
            if not success:
                test_results["issues"].append(f"Failed to start service: {output}")
                test_results["recommendations"].append("Check Docker Compose configuration")
                return test_results
            
            # Step 5: Wait and check startup logs
            logger.info(f"⏳ Waiting for {service_name} to initialize...")
            await asyncio.sleep(10)  # Give service time to start
            
            startup_issues = self.check_startup_logs(service_name)
            test_results["issues"].extend(startup_issues)
            
            # Step 6: Check health with extended timeout
            health_success = await self.check_service_health(service_name, port, max_attempts=60)
            test_results["health_check_success"] = health_success
            
            # Step 7: Generate recommendations based on issues
            if startup_issues:
                if any("jwt" in issue.lower() for issue in startup_issues):
                    test_results["recommendations"].append("Fix JWT dependency issues in requirements.txt")
                if any("modulenotfounderror" in issue.lower() for issue in startup_issues):
                    test_results["recommendations"].append("Add missing Python packages to requirements.txt")
                if any("connection" in issue.lower() for issue in startup_issues):
                    test_results["recommendations"].append("Check database/Redis/RabbitMQ connectivity")
            
            if not health_success:
                test_results["recommendations"].append("Service failed to respond to health checks - check application startup")
            
        except Exception as e:
            logger.error(f"❌ Exception during {service_name} testing: {e}")
            test_results["issues"].append(f"Exception: {e}")
        
        finally:
            # Stop the service
            logger.info(f"🛑 Stopping {service_name}...")
            self.run_docker_command(f"docker-compose stop {service_name}")
        
        # Log results
        if test_results["health_check_success"]:
            logger.info(f"✅ {service_name} startup test PASSED")
        else:
            logger.error(f"❌ {service_name} startup test FAILED")
            logger.error(f"   Issues: {test_results['issues']}")
            logger.info(f"   Recommendations: {test_results['recommendations']}")
        
        return test_results
    
    async def run_startup_tests(self) -> Dict:
        """Run startup tests on all failing services"""
        logger.info("🚀 Starting Priority 2: Service Startup Testing")
        logger.info("=" * 80)
        
        results = {
            "services_tested": [],
            "successful_services": [],
            "failed_services": [],
            "summary": {}
        }
        
        for service in self.failing_services:
            service_result = await self.test_individual_service_startup(service)
            results["services_tested"].append(service_result)
            
            if service_result["health_check_success"]:
                results["successful_services"].append(service["name"])
            else:
                results["failed_services"].append(service["name"])
        
        # Generate summary
        total_services = len(self.failing_services)
        successful_count = len(results["successful_services"])
        failed_count = len(results["failed_services"])
        
        results["summary"] = {
            "total_services": total_services,
            "successful_count": successful_count,
            "failed_count": failed_count,
            "success_rate": successful_count / total_services if total_services > 0 else 0
        }
        
        # Print summary
        self.print_summary(results)
        
        return results
    
    def print_summary(self, results: Dict):
        """Print test summary"""
        logger.info("\n" + "=" * 80)
        logger.info("🎯 PRIORITY 2 STARTUP TESTING SUMMARY")
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
        
        # Detailed recommendations
        logger.info(f"\n📋 DETAILED ISSUES AND RECOMMENDATIONS:")
        for service_result in results["services_tested"]:
            if not service_result["health_check_success"]:
                service_name = service_result["service_name"]
                logger.info(f"\n{service_name}:")
                for issue in service_result["issues"]:
                    logger.info(f"   ❌ {issue}")
                for rec in service_result["recommendations"]:
                    logger.info(f"   💡 {rec}")

async def main():
    """Main entry point"""
    tester = ServiceStartupTester()
    results = await tester.run_startup_tests()
    
    success_rate = results["summary"]["success_rate"]
    
    if success_rate >= 0.8:  # 80% success rate
        logger.info("🎉 Priority 2 service startup testing completed successfully!")
        sys.exit(0)
    else:
        logger.error("❌ Priority 2 service startup testing failed")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
