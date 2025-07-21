"""
Kubernetes Agent for KRATOS
Manages multiple Kubernetes clusters via MCP integration
"""

import asyncio
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import yaml

from scripts.aks_mcp_wrapper import MultiClusterMCPWrapper

logger = logging.getLogger(__name__)

class K8sAgent:
    """Kubernetes Agent for multi-cluster management operations"""
    
    def __init__(self, config: Dict[str, Any]):
        self.name = "k8s-agent"
        self.config = config
        self.mcp_wrapper = None
        self.initialized = False
        self.capabilities = [
            "cluster_management",
            "multi_cluster_operations",
            "pod_operations", 
            "deployment_management",
            "monitoring",
            "yaml_operations"
        ]
        
    async def initialize(self) -> bool:
        """Initialize the agent with MCP wrapper"""
        try:
            self.mcp_wrapper = MultiClusterMCPWrapper(
                mcp_endpoint=self.config.get("mcp_endpoint")
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
                "name": "list_clusters",
                "description": "List all available Kubernetes clusters",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "switch_cluster",
                "description": "Switch to a different Kubernetes cluster",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "cluster_name": {
                            "type": "string",
                            "description": "Name of the cluster to switch to"
                        }
                    },
                    "required": ["cluster_name"]
                }
            },
            {
                "name": "get_pods",
                "description": "Get all pods in a specified namespace and cluster",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "namespace": {
                            "type": "string",
                            "description": "Kubernetes namespace",
                            "default": "default"
                        },
                        "cluster": {
                            "type": "string",
                            "description": "Kubernetes cluster name (optional)"
                        }
                    },
                    "required": []
                }
            },
            {
                "name": "restart_deployment", 
                "description": "Restart a deployment in a specified namespace and cluster",
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
                        },
                        "cluster": {
                            "type": "string",
                            "description": "Kubernetes cluster name (optional)"
                        }
                    },
                    "required": ["deployment_name"]
                }
            },
            {
                "name": "apply_yaml",
                "description": "Apply Kubernetes YAML manifest to a cluster",
                "parameters": {
                    "type": "object", 
                    "properties": {
                        "yaml_content": {
                            "type": "string",
                            "description": "YAML manifest content to apply"
                        },
                        "cluster": {
                            "type": "string",
                            "description": "Kubernetes cluster name (optional)"
                        }
                    },
                    "required": ["yaml_content"]
                }
            },
            {
                "name": "get_node_metrics",
                "description": "Get node metrics and resource information for a cluster",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "cluster": {
                            "type": "string",
                            "description": "Kubernetes cluster name (optional)"
                        }
                    },
                    "required": []
                }
            },
            {
                "name": "get_cluster_health",
                "description": "Get overall cluster health and status information for a cluster", 
                "parameters": {
                    "type": "object",
                    "properties": {
                        "cluster": {
                            "type": "string",
                            "description": "Kubernetes cluster name (optional)"
                        }
                    },
                    "required": []
                }
            },
            {
                "name": "scale_deployment",
                "description": "Scale a deployment to specified number of replicas in a cluster",
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
                        },
                        "cluster": {
                            "type": "string",
                            "description": "Kubernetes cluster name (optional)"
                        }
                    },
                    "required": ["deployment_name", "replicas"]
                }
            },
            {
                "name": "get_logs",
                "description": "Get logs from a pod in a cluster",
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
                        },
                        "cluster": {
                            "type": "string",
                            "description": "Kubernetes cluster name (optional)"
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
                "list_clusters": self.list_clusters,
                "switch_cluster": self.switch_cluster,
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
    
    async def list_clusters(self) -> Dict[str, Any]:
        """List available clusters"""
        clusters = await self.mcp_wrapper.list_clusters()
        return {
            "status": "success",
            "cluster_count": len(clusters),
            "clusters": clusters
        }
    
    async def switch_cluster(self, cluster_name: str) -> Dict[str, Any]:
        """Switch to a different cluster"""
        return await self.mcp_wrapper.switch_cluster(cluster_name)
    
    async def get_pods(self, namespace: str = "default", cluster: Optional[str] = None) -> Dict[str, Any]:
        """Get pods in a namespace"""
        pods = await self.mcp_wrapper.get_pods(namespace, cluster)
        return {
            "status": "success",
            "namespace": namespace,
            "cluster": cluster or self.mcp_wrapper.current_cluster,
            "pod_count": len(pods),
            "pods": pods
        }
    
    async def restart_deployment(self, deployment_name: str, namespace: str = "default", cluster: Optional[str] = None) -> Dict[str, Any]:
        """Restart a deployment"""
        return await self.mcp_wrapper.restart_deployment(namespace, deployment_name, cluster)
    
    async def apply_yaml(self, yaml_content: str, cluster: Optional[str] = None) -> Dict[str, Any]:
        """Apply YAML manifest"""
        return await self.mcp_wrapper.apply_yaml(yaml_content, cluster)
    
    async def get_node_metrics(self, cluster: Optional[str] = None) -> Dict[str, Any]:
        """Get node metrics"""
        return await self.mcp_wrapper.get_node_metrics(cluster)
    
    async def get_cluster_health(self, cluster: Optional[str] = None) -> Dict[str, Any]:
        """Get cluster health"""
        return await self.mcp_wrapper.get_cluster_health(cluster)
    
    async def scale_deployment(self, deployment_name: str, replicas: int, namespace: str = "default", cluster: Optional[str] = None) -> Dict[str, Any]:
        """Scale a deployment"""
        try:
            # Switch cluster if specified
            if cluster and cluster != self.mcp_wrapper.current_cluster:
                switch_result = await self.mcp_wrapper.switch_cluster(cluster)
                if switch_result["status"] != "success":
                    return switch_result
            
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
                "cluster": cluster or self.mcp_wrapper.current_cluster,
                "replicas": replicas
            }
            
        except Exception as e:
            logger.error(f"Failed to scale deployment: {e}")
            return {
                "status": "error", 
                "message": str(e),
                "deployment": deployment_name,
                "namespace": namespace,
                "cluster": cluster or self.mcp_wrapper.current_cluster
            }
    
    async def get_logs(self, pod_name: str, namespace: str = "default", 
                      container_name: Optional[str] = None, tail_lines: int = 100, cluster: Optional[str] = None) -> Dict[str, Any]:
        """Get pod logs"""
        try:
            # Switch cluster if specified
            if cluster and cluster != self.mcp_wrapper.current_cluster:
                switch_result = await self.mcp_wrapper.switch_cluster(cluster)
                if switch_result["status"] != "success":
                    return switch_result
            
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
                "cluster": cluster or self.mcp_wrapper.current_cluster,
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
                "namespace": namespace,
                "cluster": cluster or self.mcp_wrapper.current_cluster
            }

    def get_status(self) -> Dict[str, Any]:
        """Get agent status"""
        cluster_info = {}
        if self.mcp_wrapper:
            cluster_info = {
                "current_cluster": self.mcp_wrapper.current_cluster,
                "available_clusters": list(self.mcp_wrapper.clusters.keys())
            }
        
        return {
            "name": self.name,
            "initialized": self.initialized,
            "capabilities": self.capabilities,
            "cluster_info": cluster_info,
            "config": {
                "mcp_endpoint": self.config.get("mcp_endpoint", "not configured")
            }
        }