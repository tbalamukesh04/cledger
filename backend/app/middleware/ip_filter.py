import os
import ipaddress
import logging
from fastapi import Request, HTTPException, status

logger = logging.getLogger(__name__)

class IPFilter:
    """
    Dependency-based IP filtering to restrict access to specific routes.
    Supports both single IPs and CIDR blocks dynamically via environment variables.
    """
    def __init__(self, allowed_ips_env_key: str = None, blocked_ips_env_key: str = None):
        self.allowed_ips_env_key = allowed_ips_env_key
        self.blocked_ips_env_key = blocked_ips_env_key

    def _get_networks(self, env_key: str) -> list:
        if not env_key:
            return []
        
        val = os.getenv(env_key, "").strip()
        if not val:
            return []
        
        networks = []
        for ip_str in val.split(","):
            ip_str = ip_str.strip()
            if ip_str:
                try:
                    networks.append(ipaddress.ip_network(ip_str, strict=False))
                except ValueError:
                    logger.warning(f"Invalid IP/CIDR in {env_key}: {ip_str}")
        return networks

    async def __call__(self, request: Request):
        client_ip = request.client.host if request.client else None
        
        if client_ip == "testclient":
            client_ip = "127.0.0.1"
        if not client_ip:
            logger.warning("IP Filter: Could not determine client IP from request")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

        try:
            client_addr = ipaddress.ip_address(client_ip)
        except ValueError:
            logger.warning(f"IP Filter: Invalid Client IP format: {client_ip}")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

        # 1. Check Blocklist first
        blocked_networks = self._get_networks(self.blocked_ips_env_key)
        if any(client_addr in net for net in blocked_networks):
            logger.warning(f"Blocked IP attempted access: {client_ip} on {request.url.path}")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

        # 2. Check Allowlist (If configured, denies everything else by default)
        allowed_networks = self._get_networks(self.allowed_ips_env_key)
        if allowed_networks:
            if not any(client_addr in net for net in allowed_networks):
                logger.warning(f"Unauthorized IP attempted access: {client_ip} on {request.url.path}")
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
