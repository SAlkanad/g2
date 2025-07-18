"""
Network Monitoring and Health Check Module
Monitors network connectivity and provides health status for Firebase and Telegram APIs
"""

import asyncio
import logging
import time
import socket
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
import aiohttp
import json

logger = logging.getLogger(__name__)

class NetworkMonitor:
    """Monitor network connectivity and API health"""
    
    def __init__(self):
        self.firebase_status = {'healthy': False, 'last_check': None, 'error': None}
        self.telegram_status = {'healthy': False, 'last_check': None, 'error': None}
        self.internet_status = {'healthy': False, 'last_check': None, 'error': None}
        self.check_interval = 300  # 5 minutes
        self.monitoring_active = False
        
    async def check_internet_connectivity(self) -> Tuple[bool, Optional[str]]:
        """Check basic internet connectivity"""
        try:
            # Test DNS resolution
            socket.gethostbyname('google.com')
            
            # Test HTTP connection
            connector = aiohttp.TCPConnector(
                limit=5,
                enable_cleanup_closed=True
            )
            
            async with aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get('https://httpbin.org/get') as response:
                    if response.status == 200:
                        return True, None
                    else:
                        return False, f"HTTP status: {response.status}"
                        
        except Exception as e:
            return False, str(e)
    
    async def check_firebase_connectivity(self) -> Tuple[bool, Optional[str]]:
        """Check Firebase connectivity"""
        try:
            # Test Firebase endpoints
            endpoints = [
                'https://firebase.googleapis.com',
                'https://firestore.googleapis.com'
            ]
            
            connector = aiohttp.TCPConnector(
                limit=5,
                enable_cleanup_closed=True
            )
            
            async with aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=15)) as session:
                for endpoint in endpoints:
                    try:
                        async with session.get(endpoint) as response:
                            # Any response (even 4xx) indicates connectivity
                            if response.status < 500:
                                continue
                            else:
                                return False, f"Firebase endpoint {endpoint} returned {response.status}"
                    except Exception as e:
                        return False, f"Firebase endpoint {endpoint} failed: {e}"
                        
            return True, None
            
        except Exception as e:
            return False, str(e)
    
    async def check_telegram_connectivity(self) -> Tuple[bool, Optional[str]]:
        """Check Telegram API connectivity"""
        try:
            # Test Telegram API endpoints with more comprehensive list
            endpoints = [
                'https://api.telegram.org',
                'https://149.154.167.50',  # Telegram DC1
                'https://149.154.175.50',  # Telegram DC2
                'https://149.154.175.100', # Telegram DC3
                'https://149.154.167.91',  # Telegram DC4
                'https://149.154.171.5',   # Telegram DC5
                'https://telegram.org',    # Main Telegram site
            ]
            
            connector = aiohttp.TCPConnector(
                limit=10,
                enable_cleanup_closed=True,
                force_close=True,
                limit_per_host=3
            )
            
            successful_endpoints = []
            failed_endpoints = []
            
            async with aiohttp.ClientSession(
                connector=connector, 
                timeout=aiohttp.ClientTimeout(total=20, connect=5)
            ) as session:
                for endpoint in endpoints:
                    try:
                        async with session.get(endpoint, allow_redirects=True) as response:
                            # Any response indicates connectivity
                            if response.status < 500:
                                successful_endpoints.append(endpoint)
                                logger.debug(f"Telegram endpoint {endpoint} accessible (status: {response.status})")
                            else:
                                failed_endpoints.append(f"{endpoint} (status: {response.status})")
                    except asyncio.TimeoutError:
                        failed_endpoints.append(f"{endpoint} (timeout)")
                        logger.debug(f"Telegram endpoint {endpoint} timed out")
                        continue
                    except Exception as e:
                        failed_endpoints.append(f"{endpoint} ({str(e)})")
                        logger.debug(f"Telegram endpoint {endpoint} failed: {e}")
                        continue
                        
            # Consider it successful if at least one endpoint is reachable
            if successful_endpoints:
                logger.info(f"Telegram connectivity OK - {len(successful_endpoints)}/{len(endpoints)} endpoints accessible")
                return True, None
            else:
                error_msg = f"All Telegram endpoints unreachable. Failed endpoints: {', '.join(failed_endpoints[:3])}"
                logger.error(error_msg)
                return False, error_msg
            
        except Exception as e:
            return False, str(e)
    
    async def perform_health_check(self) -> Dict:
        """Perform comprehensive health check"""
        logger.info("Performing network health check...")
        
        # Check internet connectivity
        internet_healthy, internet_error = await self.check_internet_connectivity()
        self.internet_status = {
            'healthy': internet_healthy,
            'last_check': datetime.now(),
            'error': internet_error
        }
        
        # Check Firebase connectivity
        firebase_healthy, firebase_error = await self.check_firebase_connectivity()
        self.firebase_status = {
            'healthy': firebase_healthy,
            'last_check': datetime.now(),
            'error': firebase_error
        }
        
        # Check Telegram connectivity
        telegram_healthy, telegram_error = await self.check_telegram_connectivity()
        self.telegram_status = {
            'healthy': telegram_healthy,
            'last_check': datetime.now(),
            'error': telegram_error
        }
        
        health_report = {
            'internet': self.internet_status,
            'firebase': self.firebase_status,
            'telegram': self.telegram_status,
            'overall_healthy': internet_healthy and firebase_healthy and telegram_healthy,
            'check_time': datetime.now().isoformat()
        }
        
        # Log health status
        status_msg = f"Network Health - Internet: {'✓' if internet_healthy else '✗'}, Firebase: {'✓' if firebase_healthy else '✗'}, Telegram: {'✓' if telegram_healthy else '✗'}"
        if health_report['overall_healthy']:
            logger.info(status_msg)
        else:
            logger.warning(status_msg)
            if internet_error:
                logger.error(f"Internet connectivity issue: {internet_error}")
            if firebase_error:
                logger.error(f"Firebase connectivity issue: {firebase_error}")
            if telegram_error:
                logger.error(f"Telegram connectivity issue: {telegram_error}")
        
        return health_report
    
    async def start_monitoring(self):
        """Start continuous network monitoring"""
        self.monitoring_active = True
        logger.info(f"Starting network monitoring with {self.check_interval}s interval")
        
        while self.monitoring_active:
            try:
                await self.perform_health_check()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                logger.info("Network monitoring cancelled")
                break
            except Exception as e:
                logger.error(f"Error in network monitoring: {e}")
                await asyncio.sleep(30)  # Wait before retry
    
    def stop_monitoring(self):
        """Stop network monitoring"""
        self.monitoring_active = False
        logger.info("Network monitoring stopped")
    
    def get_health_status(self) -> Dict:
        """Get current health status"""
        return {
            'internet': self.internet_status,
            'firebase': self.firebase_status,
            'telegram': self.telegram_status,
            'overall_healthy': (
                self.internet_status['healthy'] and 
                self.firebase_status['healthy'] and 
                self.telegram_status['healthy']
            )
        }
    
    def is_service_healthy(self, service: str) -> bool:
        """Check if a specific service is healthy"""
        status_map = {
            'internet': self.internet_status,
            'firebase': self.firebase_status,
            'telegram': self.telegram_status
        }
        
        if service not in status_map:
            return False
        
        status = status_map[service]
        
        # Check if status is recent (within last 10 minutes)
        if status['last_check']:
            age = datetime.now() - status['last_check']
            if age > timedelta(minutes=10):
                return False
        
        return status['healthy']
    
    async def wait_for_service_health(self, service: str, timeout: int = 120) -> bool:
        """Wait for a service to become healthy"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if self.is_service_healthy(service):
                return True
            
            # Perform health check
            await self.perform_health_check()
            
            # Wait before next check
            await asyncio.sleep(10)
        
        return False
    
    def get_recommendations(self) -> Dict:
        """Get recommendations based on current health status"""
        recommendations = {
            'actions': [],
            'settings': {}
        }
        
        if not self.internet_status['healthy']:
            recommendations['actions'].append("Check internet connection")
            recommendations['settings']['use_offline_mode'] = True
        
        if not self.firebase_status['healthy']:
            recommendations['actions'].append("Disable Firebase sync temporarily")
            recommendations['settings']['firebase_enabled'] = False
            recommendations['settings']['local_storage_only'] = True
        
        if not self.telegram_status['healthy']:
            recommendations['actions'].append("Increase Telegram timeout settings")
            recommendations['actions'].append("Enable Telegram fallback mode")
            recommendations['settings']['telegram_timeout'] = 180
            recommendations['settings']['telegram_retries'] = 10
            recommendations['settings']['telegram_fallback_enabled'] = True
            recommendations['settings']['telegram_connection_retries'] = 5
        
        return recommendations
    
    async def handle_telegram_connectivity_issues(self) -> Dict:
        """Handle Telegram connectivity issues with fallback strategies"""
        try:
            logger.info("Handling Telegram connectivity issues...")
            
            # First, try a comprehensive health check
            await self.perform_health_check()
            
            if self.telegram_status['healthy']:
                return {'status': 'recovered', 'message': 'Telegram connectivity restored'}
            
            # If still unhealthy, try alternative approaches
            recommendations = self.get_recommendations()
            
            # Wait for potential recovery
            logger.info("Waiting for Telegram connectivity recovery...")
            recovery_attempts = 0
            max_recovery_attempts = 3
            
            while recovery_attempts < max_recovery_attempts:
                await asyncio.sleep(30)  # Wait 30 seconds between attempts
                
                # Check connectivity again
                healthy, error = await self.check_telegram_connectivity()
                if healthy:
                    logger.info("Telegram connectivity recovered!")
                    self.telegram_status = {
                        'healthy': True,
                        'last_check': datetime.now(),
                        'error': None
                    }
                    return {'status': 'recovered', 'message': 'Telegram connectivity recovered after retry'}
                
                recovery_attempts += 1
                logger.warning(f"Telegram recovery attempt {recovery_attempts}/{max_recovery_attempts} failed")
            
            # If all recovery attempts failed, return current recommendations
            return {
                'status': 'failed',
                'message': 'Telegram connectivity could not be restored',
                'recommendations': recommendations
            }
            
        except Exception as e:
            logger.error(f"Error handling Telegram connectivity issues: {e}")
            return {'status': 'error', 'message': str(e)}


# Global network monitor instance
network_monitor = NetworkMonitor()


async def initialize_network_monitoring():
    """Initialize network monitoring"""
    try:
        # Perform initial health check
        await network_monitor.perform_health_check()
        
        # Start monitoring in background
        asyncio.create_task(network_monitor.start_monitoring())
        
        logger.info("Network monitoring initialized successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize network monitoring: {e}")


def get_network_health() -> Dict:
    """Get current network health status"""
    return network_monitor.get_health_status()


async def ensure_service_health(service: str, timeout: int = 60) -> bool:
    """Ensure a service is healthy before proceeding"""
    if not network_monitor.is_service_healthy(service):
        logger.warning(f"Service {service} is not healthy, waiting for recovery...")
        return await network_monitor.wait_for_service_health(service, timeout)
    return True