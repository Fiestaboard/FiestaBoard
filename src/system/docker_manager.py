"""Docker container management for production environments."""

import os
import logging
import time
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class DockerManager:
    """Manages Docker containers via Docker API (production only)."""
    
    def __init__(self):
        """Initialize Docker manager with production check."""
        self.is_production = os.getenv("PRODUCTION", "false").lower() == "true"
        self.client = None
        
        if not self.is_production:
            logger.warning("DockerManager initialized in non-production mode - operations will be blocked")
            return
            
        try:
            import docker
            self.client = docker.from_env()
            logger.info("DockerManager initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Docker client: {e}")
            raise RuntimeError(f"Docker client initialization failed: {e}")
    
    def _check_production(self):
        """Ensure we're running in production mode."""
        if not self.is_production:
            raise PermissionError("System management operations are only available in production mode")
        if not self.client:
            raise RuntimeError("Docker client not initialized")
    
    def get_container_status(self) -> Dict[str, Any]:
        """Get status of all FiestaBoard containers."""
        self._check_production()
        
        try:
            containers = self.client.containers.list(all=True)
            fiesta_containers = [c for c in containers if 'fiestaboard' in c.name.lower()]
            
            status = {
                "containers": [],
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
            
            for container in fiesta_containers:
                container_info = {
                    "name": container.name,
                    "status": container.status,
                    "image": container.image.tags[0] if container.image.tags else "unknown",
                    "created": container.attrs.get("Created", ""),
                    "started": container.attrs.get("State", {}).get("StartedAt", ""),
                    "health": container.attrs.get("State", {}).get("Health", {}).get("Status", "none")
                }
                status["containers"].append(container_info)
            
            return status
        except Exception as e:
            logger.error(f"Failed to get container status: {e}")
            raise RuntimeError(f"Failed to get container status: {e}")
    
    def restart_container(self, service_name: str, delay: int = 0) -> Dict[str, str]:
        """
        Restart a specific container.
        
        Args:
            service_name: Service name (api, ui, or all)
            delay: Delay in seconds before restarting (useful for API restarts)
        
        Returns:
            Result dictionary with status message
        """
        self._check_production()
        
        if delay > 0:
            logger.info(f"Waiting {delay} seconds before restarting {service_name}...")
            time.sleep(delay)
        
        try:
            containers = self.client.containers.list()
            
            if service_name == "all":
                target_containers = [c for c in containers if 'fiestaboard' in c.name.lower()]
                container_names = [c.name for c in target_containers]
            else:
                # Map service names to container names
                service_map = {
                    "api": "fiestaboard",
                    "ui": "fiestaboard"
                }
                container_name = service_map.get(service_name)
                if not container_name:
                    raise ValueError(f"Unknown service: {service_name}")
                
                target_containers = [c for c in containers if container_name in c.name]
                container_names = [c.name for c in target_containers]
            
            if not target_containers:
                raise RuntimeError(f"No containers found for service: {service_name}")
            
            # Restart each container
            for container in target_containers:
                logger.info(f"Restarting container: {container.name}")
                container.restart(timeout=10)
            
            return {
                "status": "success",
                "message": f"Restarted {len(target_containers)} container(s): {', '.join(container_names)}"
            }
        except Exception as e:
            logger.error(f"Failed to restart container(s): {e}")
            raise RuntimeError(f"Failed to restart container(s): {e}")
    
    def upgrade_containers(self) -> Dict[str, str]:
        """
        Pull latest images and restart all containers.
        
        This performs the equivalent of:
        docker-compose pull && docker-compose up -d
        """
        self._check_production()
        
        try:
            logger.info("Starting container upgrade process...")
            
            # Get all FiestaBoard containers
            containers = self.client.containers.list(all=True)
            fiesta_containers = [c for c in containers if 'fiestaboard' in c.name.lower()]
            
            if not fiesta_containers:
                raise RuntimeError("No FiestaBoard containers found")
            
            # Pull latest images for each container
            images_pulled = []
            for container in fiesta_containers:
                image_name = container.image.tags[0] if container.image.tags else None
                if image_name:
                    logger.info(f"Pulling latest image: {image_name}")
                    try:
                        self.client.images.pull(image_name)
                        images_pulled.append(image_name)
                    except Exception as e:
                        logger.warning(f"Failed to pull image {image_name}: {e}")
            
            # Restart containers to use new images
            if images_pulled:
                logger.info("Images pulled, restarting containers...")
                for container in fiesta_containers:
                    container.restart(timeout=10)
                
                return {
                    "status": "success",
                    "message": f"Upgraded {len(images_pulled)} image(s) and restarted containers"
                }
            else:
                return {
                    "status": "success",
                    "message": "No images were updated (already at latest versions)"
                }
        except Exception as e:
            logger.error(f"Failed to upgrade containers: {e}")
            raise RuntimeError(f"Failed to upgrade containers: {e}")
    
    def get_container_logs(self, service_name: str, lines: int = 100) -> List[str]:
        """
        Get logs from a specific container.
        
        Args:
            service_name: Service name (api, ui, or all)
            lines: Number of lines to retrieve (tail)
        
        Returns:
            List of log lines
        """
        self._check_production()
        
        try:
            containers = self.client.containers.list()
            
            # Map service names to container names
            service_map = {
                "api": "fiestaboard",
                "ui": "fiestaboard",
                "all": "fiestaboard"
            }
            
            search_term = service_map.get(service_name, service_name)
            target_containers = [c for c in containers if search_term in c.name.lower()]
            
            if not target_containers:
                return [f"No containers found for service: {service_name}"]
            
            all_logs = []
            for container in target_containers:
                all_logs.append(f"=== Logs from {container.name} ===")
                logs = container.logs(tail=lines, timestamps=True).decode('utf-8')
                all_logs.extend(logs.splitlines())
                all_logs.append("")  # Empty line between containers
            
            return all_logs
        except Exception as e:
            logger.error(f"Failed to get container logs: {e}")
            raise RuntimeError(f"Failed to get container logs: {e}")


# Global instance
_docker_manager: Optional[DockerManager] = None


def get_docker_manager() -> DockerManager:
    """Get or create the global DockerManager instance."""
    global _docker_manager
    if _docker_manager is None:
        _docker_manager = DockerManager()
    return _docker_manager

