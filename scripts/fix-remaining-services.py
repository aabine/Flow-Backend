#!/usr/bin/env python3
"""
Fix Remaining Services Script
Apply Docker optimizations and JWT fixes to remaining failing services
"""

import os
import subprocess
import logging
import sys

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ServiceFixer:
    """Fix Docker and JWT issues for remaining services"""
    
    def __init__(self):
        self.remaining_services = [
            "supplier-onboarding-service",
            "pricing-service", 
            "delivery-service",
            "notification-service",
            "admin-service",
            "websocket-service"
        ]
        
    def fix_dockerfile(self, service_name: str) -> bool:
        """Fix Dockerfile to optimize build context and paths"""
        dockerfile_path = f"{service_name}/Dockerfile"
        
        if not os.path.exists(dockerfile_path):
            logger.error(f"❌ Dockerfile not found: {dockerfile_path}")
            return False
        
        logger.info(f"🔧 Fixing Dockerfile for {service_name}")
        
        try:
            # Read current Dockerfile
            with open(dockerfile_path, 'r') as f:
                content = f.read()
            
            # Check if already optimized
            if f"COPY {service_name}/" in content:
                logger.info(f"✅ {service_name} Dockerfile already optimized")
                return True
            
            # Apply optimizations
            optimized_content = content.replace(
                "# Copy requirements first for better caching\nCOPY requirements.txt .",
                f"# Copy requirements first for better caching\nCOPY {service_name}/requirements.txt ."
            ).replace(
                "# Copy application code\nCOPY . .",
                f"# Copy shared modules\nCOPY shared/ ./shared/\n\n# Copy application code\nCOPY {service_name}/ ./{service_name}/"
            )
            
            # Write optimized Dockerfile
            with open(dockerfile_path, 'w') as f:
                f.write(optimized_content)
            
            logger.info(f"✅ {service_name} Dockerfile optimized")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to fix {service_name} Dockerfile: {e}")
            return False
    
    def run_command(self, command: str, timeout: int = 180) -> tuple:
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
    
    def build_service(self, service_name: str) -> bool:
        """Build service with optimized Dockerfile"""
        logger.info(f"🏗️ Building {service_name}...")
        
        success, stdout, stderr = self.run_command(f"docker-compose build {service_name}")
        
        if success:
            logger.info(f"✅ {service_name} build successful")
            return True
        else:
            logger.error(f"❌ {service_name} build failed: {stderr}")
            return False
    
    def test_service_startup(self, service_name: str, port: int) -> bool:
        """Test service startup and health check"""
        logger.info(f"🧪 Testing {service_name} startup...")
        
        # Start dependencies
        self.run_command("docker-compose up -d postgres redis rabbitmq")
        
        # Start service
        success, _, _ = self.run_command(f"docker-compose up -d {service_name}")
        if not success:
            logger.error(f"❌ Failed to start {service_name}")
            return False
        
        # Wait for startup
        import time
        time.sleep(10)
        
        # Test health endpoint
        success, _, _ = self.run_command(f"curl -f http://localhost:{port}/health", timeout=10)
        
        # Stop service
        self.run_command(f"docker-compose stop {service_name}")
        
        if success:
            logger.info(f"✅ {service_name} startup test passed")
            return True
        else:
            logger.error(f"❌ {service_name} startup test failed")
            return False
    
    def fix_all_services(self) -> dict:
        """Fix all remaining services"""
        logger.info("🚀 Starting to fix remaining services")
        
        results = {
            "fixed_services": [],
            "failed_services": [],
            "summary": {}
        }
        
        service_ports = {
            "supplier-onboarding-service": 8002,
            "pricing-service": 8006,
            "delivery-service": 8007,
            "notification-service": 8010,
            "admin-service": 8011,
            "websocket-service": 8012
        }
        
        for service_name in self.remaining_services:
            logger.info(f"\n{'='*60}")
            logger.info(f"🔧 FIXING {service_name.upper()}")
            logger.info(f"{'='*60}")
            
            # Step 1: Fix Dockerfile
            dockerfile_fixed = self.fix_dockerfile(service_name)
            if not dockerfile_fixed:
                results["failed_services"].append(service_name)
                continue
            
            # Step 2: Build service
            build_success = self.build_service(service_name)
            if not build_success:
                results["failed_services"].append(service_name)
                continue
            
            # Step 3: Test startup
            port = service_ports.get(service_name, 8000)
            startup_success = self.test_service_startup(service_name, port)
            
            if startup_success:
                results["fixed_services"].append(service_name)
                logger.info(f"🎉 {service_name} successfully fixed!")
            else:
                results["failed_services"].append(service_name)
                logger.error(f"💥 {service_name} still has issues")
        
        # Generate summary
        total_services = len(self.remaining_services)
        fixed_count = len(results["fixed_services"])
        failed_count = len(results["failed_services"])
        
        results["summary"] = {
            "total_services": total_services,
            "fixed_count": fixed_count,
            "failed_count": failed_count,
            "success_rate": fixed_count / total_services if total_services > 0 else 0
        }
        
        self.print_summary(results)
        return results
    
    def print_summary(self, results: dict):
        """Print fix summary"""
        logger.info("\n" + "=" * 80)
        logger.info("🎯 SERVICE FIXING SUMMARY")
        logger.info("=" * 80)
        
        summary = results["summary"]
        logger.info(f"📊 Total Services Fixed: {summary['total_services']}")
        logger.info(f"✅ Successfully Fixed: {summary['fixed_count']}")
        logger.info(f"❌ Still Failing: {summary['failed_count']}")
        logger.info(f"📈 Fix Success Rate: {summary['success_rate']:.1%}")
        
        if results["fixed_services"]:
            logger.info(f"\n✅ SUCCESSFULLY FIXED SERVICES:")
            for service in results["fixed_services"]:
                logger.info(f"   - {service}")
        
        if results["failed_services"]:
            logger.info(f"\n❌ STILL FAILING SERVICES:")
            for service in results["failed_services"]:
                logger.info(f"   - {service}")

def main():
    """Main entry point"""
    fixer = ServiceFixer()
    results = fixer.fix_all_services()
    
    success_rate = results["summary"]["success_rate"]
    
    if success_rate >= 0.8:  # 80% success rate
        logger.info("🎉 Service fixing completed successfully!")
        sys.exit(0)
    else:
        logger.error("❌ Some services still need fixing")
        sys.exit(1)

if __name__ == "__main__":
    main()
