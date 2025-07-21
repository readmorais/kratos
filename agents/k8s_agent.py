"""
Kubernetes Agent for KRATOS
Manages Azure Kubernetes Service operations via MCP integration
"""

import asyncio
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import yaml

from scripts.aks_mcp_wrapper import AKSMCPWrapper

logger = logging.getLogger(__name__)

class K8sAgent:
    """Kubernetes Agent for cluster management operations"""
    
    def __init__(self, config: Dict[str, Any]):
        self.name = "k8s-agent"
        self.config = config
        self.mcp_wrapper = None
        self.initialized = False
        self.capabilities = [
            "cluster_management",
            "pod_operations", 
            "deployment_management",
            "monitoring",
            "yaml_operations"
        ]
        
    async def initialize(self) -> bool:
        """Initialize the agent with MCP wrapper"""
        try:
            self.mcp_wrapper = AKSMCPWrapper(
                mcp_endpoint=self.config.get("mcp_endpoint"),
                subscription_id=self.config.get("subscription_id"),
                resource_group=self.config.get("resource_group"),
                cluster_name=self.config.get("cluster_name")
            )
            
            self.initialized = await self.mcp_wrapper.initialize()
            
            if self.initialized:
                logger.info(f"K8s Agent {self.name} initialized successfully")
            else:
                logger.error(f"Failed to initialize K8s Agent {self.name}")
                
            return self.initialized
            
        except Exception as e:
            logger.error(f"Error initializing K8s Agent: {e}")
            return False
    
    def get_function_definitions(self) -> List[Dict[str, Any]]:
        """Return function definitions for AutoGen"""
        return [
            {
                "name": "get_pods",
                "description": "Get all pods in a specified namespace",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "namespace": {
                            "type": "string",
                            "description": "Kubernetes namespace",
                            "default": "default"
                        }
                    },
                    "required": []
                }
            },
            {
                "name": "restart_deployment", 
                "description": "Restart a deployment in a specified namespace",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "namespace": {
                            "type": "string", 
                            "description": "Kubernetes namespace",
                            "default": "default"
                        },
                        "deployment_name": {
                            "type": "string",
                            "description": "Name of the deployment to restart"
                        }
                    },
                    "required": ["deployment_name"]
                }
            },
            {
                "name": "apply_yaml",
                "description": "Apply Kubernetes YAML manifest to the cluster",
                "parameters": {
                    "type": "object", 
                    "properties": {
                        "yaml_content": {
                            "type": "string",
                            "description": "YAML manifest content to apply"
                        }
                    },
                    "required": ["yaml_content"]
                }
            },
            {
                "name": "get_node_metrics",
                "description": "Get node metrics and resource information",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "get_cluster_health",
                "description": "Get overall cluster health and status information", 
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "scale_deployment",
                "description": "Scale a deployment to specified number of replicas",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "namespace": {
                            "type": "string",
                            "description": "Kubernetes namespace", 
                            "default": "default"
                        },
                        "deployment_name": {
                            "type": "string",
                            "description": "Name of the deployment to scale"
                        },
                        "replicas": {
                            "type": "integer",
                            "description": "Number of replicas to scale to",
                            "minimum": 0
                        }
                    },
                    "required": ["deployment_name", "replicas"]
                }
            },
            {
                "name": "get_logs",
                "description": "Get logs from a pod",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "namespace": {
                            "type": "string",
                            "description": "Kubernetes namespace",
                            "default": "default"
                        },
                        "pod_name": {
                            "type": "string", 
                            "description": "Name of the pod to get logs from"
                        },
                        "container_name": {
                            "type": "string",
                            "description": "Container name (optional)"
                        },
                        "tail_lines": {
                            "type": "integer",
                            "description": "Number of lines to tail",
                            "default": 100
                        }
                    },
                    "required": ["pod_name"]
                }
            }
        ]
    
    async def execute_function(self, function_name: str, **kwargs) -> Dict[str, Any]:
        """Execute a function by name with given parameters"""
        if not self.initialized:
            return {
                "status": "error",
                "message": "Agent not initialized"
            }
        
        try:
            # Map function names to methods
            function_map = {
                "get_pods": self.get_pods,
                "restart_deployment": self.restart_deployment,
                "apply_yaml": self.apply_yaml, 
                "get_node_metrics": self.get_node_metrics,
                "get_cluster_health": self.get_cluster_health,
                "scale_deployment": self.scale_deployment,
                "get_logs": self.get_logs
            }
            
            if function_name not in function_map:
                return {
                    "status": "error",
                    "message": f"Unknown function: {function_name}"
                }
            
            result = await function_map[function_name](**kwargs)
            
            # Add metadata to result
            result["agent"] = self.name
            result["function"] = function_name
            result["timestamp"] = datetime.utcnow().isoformat()
            
            return result
            
        except Exception as e:
            logger.error(f"Error executing function {function_name}: {e}")
            return {
                "status": "error",
                "message": str(e),
                "agent": self.name,
                "function": function_name
            }
    
    async def get_pods(self, namespace: str = "default") -> Dict[str, Any]:
        """Get pods in a namespace"""
        pods = await self.mcp_wrapper.get_pods(namespace)
        return {
            "status": "success",
            "namespace": namespace,
            "pod_count": len(pods),
            "pods": pods
        }
    
    async def restart_deployment(self, deployment_name: str, namespace: str = "default") -> Dict[str, Any]:
        """Restart a deployment"""
        return await self.mcp_wrapper.restart_deployment(namespace, deployment_name)
    
    async def apply_yaml(self, yaml_content: str) -> Dict[str, Any]:
        """Apply YAML manifest"""
        return await self.mcp_wrapper.apply_yaml(yaml_content)
    
    async def get_node_metrics(self) -> Dict[str, Any]:
        """Get node metrics"""
        return await self.mcp_wrapper.get_node_metrics()
    
    async def get_cluster_health(self) -> Dict[str, Any]:
        """Get cluster health"""
        return await self.mcp_wrapper.get_cluster_health()
    
    async def scale_deployment(self, deployment_name: str, replicas: int, namespace: str = "default") -> Dict[str, Any]:
        """Scale a deployment"""
        try:
            from kubernetes import client
            apps_v1 = client.AppsV1Api()
            
            # Scale the deployment
            body = {"spec": {"replicas": replicas}}
            apps_v1.patch_namespaced_deployment_scale(
                name=deployment_name,
                namespace=namespace,
                body=body
            )
            
            return {
                "status": "success",
                "message": f"Deployment {deployment_name} scaled to {replicas} replicas",
                "deployment": deployment_name,
                "namespace": namespace,
                "replicas": replicas
            }
            
        except Exception as e:
            logger.error(f"Failed to scale deployment: {e}")
            return {
                "status": "error", 
                "message": str(e),
                "deployment": deployment_name,
                "namespace": namespace
            }
    
    async def get_logs(self, pod_name: str, namespace: str = "default", 
                      container_name: Optional[str] = None, tail_lines: int = 100) -> Dict[str, Any]:
        """Get pod logs"""
        try:
            from kubernetes import client
            v1 = client.CoreV1Api()
            
            logs = v1.read_namespaced_pod_log(
                name=pod_name,
                namespace=namespace,
                container=container_name,
                tail_lines=tail_lines
            )
            
            return {
                "status": "success",
                "pod": pod_name,
                "namespace": namespace,
                "container": container_name,
                "lines": tail_lines,
                "logs": logs
            }
            
        except Exception as e:
            logger.error(f"Failed to get logs: {e}")
            return {
                "status": "error",
                "message": str(e),
                "pod": pod_name,
                "namespace": namespace
            }

    def get_status(self) -> Dict[str, Any]:
        """Get agent status"""
        return {
            "name": self.name,
            "initialized": self.initialized,
            "capabilities": self.capabilities,
            "config": {k: "***" if "secret" in k.lower() or "key" in k.lower() else v 
                      for k, v in self.config.items()}
        }