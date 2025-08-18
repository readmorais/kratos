"""
AKS MCP Server Wrapper
Provides interface to multiple Kubernetes clusters via MCP protocol
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, Any
import httpx
import yaml
from kubernetes import client, config
from kubernetes.config import ConfigException

logger = logging.getLogger(__name__)

class MultiClusterMCPWrapper:
    """Wrapper for multi-cluster MCP server interactions"""
    
    def __init__(self, mcp_endpoint: str):
        self.mcp_endpoint = mcp_endpoint.rstrip('/')
        self.clusters = {}
        self.current_cluster = None
        
    async def initialize(self) -> bool:
        """Initialize available clusters"""
        try:
            logger.info("Initializing multi-cluster wrapper...")
            
            # Load kubeconfig and get available contexts
            try:
                contexts, active_context = config.list_kube_config_contexts()
                
                if not contexts:
                    logger.warning("No Kubernetes contexts found in kubeconfig")
                    return False
                
                for context in contexts:
                    cluster_name = context['name']
                    self.clusters[cluster_name] = {
                        'context': context,
                        'active': context == active_context,
                        'cluster_info': context.get('context', {})
                    }
                    
                    if context == active_context:
                        self.current_cluster = cluster_name
                        logger.info(f"Active cluster set to: {self.current_cluster}")
                
                logger.info(f"Initialized {len(self.clusters)} clusters")
                logger.info(f"Available clusters: {list(self.clusters.keys())}")
                
                # Test connection to current cluster
                if self.current_cluster:
                    try:
                        v1 = client.CoreV1Api()
                        # Try to get cluster info
                        version_api = client.VersionApi()
                        version = version_api.get_code()
                        logger.info(f"Connected to cluster {self.current_cluster}, Kubernetes version: {version.git_version}")
                    except Exception as e:
                        logger.warning(f"Could not connect to current cluster {self.current_cluster}: {e}")
                
                return len(self.clusters) > 0
                
            except ConfigException as e:
                logger.error(f"Kubeconfig error: {e}")
                logger.error("Please ensure kubectl is configured with valid cluster contexts")
                return False
                
        except Exception as e:
            logger.error(f"Failed to initialize multi-cluster wrapper: {e}")
            return False
    
    async def _test_mcp_connection(self) -> bool:
        """Test connection to MCP server"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.mcp_endpoint}/health", timeout=10.0)
                return response.status_code == 200
        except Exception as e:
            logger.error(f"MCP connection test failed: {e}")
            return False
    
    async def list_clusters(self) -> List[Dict[str, Any]]:
        """List available clusters"""
        logger.info(f"Listing {len(self.clusters)} available clusters")
        cluster_list = []
        for name, info in self.clusters.items():
            cluster_info = info.get('cluster_info', {})
            cluster_list.append({
                "name": name,
                "active": name == self.current_cluster,
                "context": cluster_info.get('cluster', 'unknown'),
                "namespace": cluster_info.get('namespace', 'default'),
                "user": cluster_info.get('user', 'unknown')
            })
        
        logger.info(f"Returning cluster list: {[c['name'] for c in cluster_list]}")
        return cluster_list
    
    async def switch_cluster(self, cluster_name: str) -> Dict[str, Any]:
        """Switch to a different cluster context"""
        try:
            logger.info(f"Attempting to switch to cluster: {cluster_name}")
            logger.info(f"Available clusters: {list(self.clusters.keys())}")
            
            if cluster_name not in self.clusters:
                available = list(self.clusters.keys())
                logger.error(f"Cluster '{cluster_name}' not found. Available: {available}")
                return {
                    "status": "error",
                    "message": f"Cluster '{cluster_name}' not found. Available clusters: {', '.join(available)}"
                }
            
            # Load the specific context
            config.load_kube_config(context=cluster_name)
            self.current_cluster = cluster_name
            
            # Test the connection
            try:
                v1 = client.CoreV1Api()
                version_api = client.VersionApi()
                version = version_api.get_code()
                logger.info(f"Successfully switched to cluster '{cluster_name}', version: {version.git_version}")
            except Exception as e:
                logger.warning(f"Switched to cluster '{cluster_name}' but connection test failed: {e}")
            
            return {
                "status": "success",
                "message": f"Switched to cluster '{cluster_name}'",
                "cluster": cluster_name
            }
            
        except Exception as e:
            logger.error(f"Failed to switch cluster: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    async def mcp_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Make a request to the MCP server"""
        try:
            # Add current cluster context to params
            if self.current_cluster:
                params["cluster"] = self.current_cluster
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.mcp_endpoint}/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": method,
                        "params": params
                    },
                    timeout=30.0
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"MCP request failed: {e}")
            return {"error": str(e)}
    
    async def get_pods(self, namespace: str = "default", cluster: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get pods in a namespace"""
        try:
            logger.info(f"Getting pods from namespace: {namespace}, cluster: {cluster}")
            # Switch cluster if specified
            if cluster and cluster != self.current_cluster:
                switch_result = await self.switch_cluster(cluster)
                if switch_result["status"] != "success":
                    return []
            
            v1 = client.CoreV1Api()
            
            # Handle "all" namespace - search across all namespaces
            if namespace == "all":
                logger.info("Searching pods across all namespaces")
                pods = v1.list_pod_for_all_namespaces()
            else:
                try:
                    pods = v1.list_namespaced_pod(namespace=namespace)
                except client.ApiException as e:
                    if e.status == 404:
                        logger.warning(f"Namespace '{namespace}' not found")
                        return []
                    else:
                        raise
            
            if not pods.items:
                logger.info(f"No pods found in namespace {namespace}")
                return []
            
            logger.info(f"Found {len(pods.items)} pods in namespace {namespace}")
            
            pod_list = []
            for pod in pods.items:
                pod_info = {
                    "name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "cluster": self.current_cluster,
                    "status": pod.status.phase,
                    "node": pod.spec.node_name,
                    "created": pod.metadata.creation_timestamp.isoformat() if pod.metadata.creation_timestamp else None,
                    "containers": [
                        {
                            "name": container.name,
                            "image": container.image,
                            "ready": any(cs.name == container.name and cs.ready for cs in (pod.status.container_statuses or []))
                        }
                        for container in pod.spec.containers
                    ]
                }
                pod_list.append(pod_info)
            
            logger.info(f"Processed {len(pod_list)} pods from namespace {namespace} in cluster {self.current_cluster}")
            return pod_list
            
        except Exception as e:
            logger.error(f"Failed to get pods: {e}")
            return []
    
    async def restart_deployment(self, namespace: str, deployment_name: str, cluster: Optional[str] = None) -> Dict[str, Any]:
        """Restart a deployment"""
        try:
            # Switch cluster if specified
            if cluster and cluster != self.current_cluster:
                switch_result = await self.switch_cluster(cluster)
                if switch_result["status"] != "success":
                    return switch_result
            
            apps_v1 = client.AppsV1Api()
            
            # Get current deployment
            deployment = apps_v1.read_namespaced_deployment(
                name=deployment_name, 
                namespace=namespace
            )
            
            # Add restart annotation
            if not deployment.spec.template.metadata.annotations:
                deployment.spec.template.metadata.annotations = {}
            
            import datetime
            deployment.spec.template.metadata.annotations["kubectl.kubernetes.io/restartedAt"] = \
                datetime.datetime.utcnow().isoformat()
            
            # Update deployment
            apps_v1.patch_namespaced_deployment(
                name=deployment_name,
                namespace=namespace,
                body=deployment
            )
            
            result = {
                "status": "success",
                "message": f"Deployment {deployment_name} restarted in namespace {namespace}",
                "deployment": deployment_name,
                "namespace": namespace,
                "cluster": self.current_cluster,
                "timestamp": datetime.datetime.utcnow().isoformat()
            }
            
            logger.info(f"Successfully restarted deployment {deployment_name} in cluster {self.current_cluster}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to restart deployment: {e}")
            return {
                "status": "error",
                "message": str(e),
                "deployment": deployment_name,
                "namespace": namespace,
                "cluster": self.current_cluster
            }
    
    async def apply_yaml(self, yaml_content: str, cluster: Optional[str] = None) -> Dict[str, Any]:
        """Apply YAML manifest to cluster"""
        try:
            # Switch cluster if specified
            if cluster and cluster != self.current_cluster:
                switch_result = await self.switch_cluster(cluster)
                if switch_result["status"] != "success":
                    return switch_result
            
            docs = yaml.safe_load_all(yaml_content)
            results = []
            
            for doc in docs:
                if not doc:
                    continue
                    
                kind = doc.get("kind")
                api_version = doc.get("apiVersion")
                metadata = doc.get("metadata", {})
                name = metadata.get("name")
                namespace = metadata.get("namespace", "default")
                
                # This is a simplified implementation
                # In production, you'd want more comprehensive resource handling
                if kind == "Deployment":
                    apps_v1 = client.AppsV1Api()
                    try:
                        apps_v1.create_namespaced_deployment(namespace=namespace, body=doc)
                        results.append({"resource": f"{kind}/{name}", "action": "created", "cluster": self.current_cluster})
                    except client.ApiException as e:
                        if e.status == 409:  # Already exists
                            apps_v1.patch_namespaced_deployment(name=name, namespace=namespace, body=doc)
                            results.append({"resource": f"{kind}/{name}", "action": "updated", "cluster": self.current_cluster})
                        else:
                            raise
                            
                elif kind == "Service":
                    v1 = client.CoreV1Api()
                    try:
                        v1.create_namespaced_service(namespace=namespace, body=doc)
                        results.append({"resource": f"{kind}/{name}", "action": "created", "cluster": self.current_cluster})
                    except client.ApiException as e:
                        if e.status == 409:
                            v1.patch_namespaced_service(name=name, namespace=namespace, body=doc)
                            results.append({"resource": f"{kind}/{name}", "action": "updated", "cluster": self.current_cluster})
                        else:
                            raise
            
            return {
                "status": "success",
                "message": f"Applied {len(results)} resources to cluster {self.current_cluster}",
                "cluster": self.current_cluster,
                "results": results
            }
            
        except Exception as e:
            logger.error(f"Failed to apply YAML: {e}")
            return {
                "status": "error",
                "message": str(e),
                "cluster": self.current_cluster
            }
    
    async def get_node_metrics(self, cluster: Optional[str] = None) -> Dict[str, Any]:
        """Get node metrics and health information"""
        try:
            # Switch cluster if specified
            if cluster and cluster != self.current_cluster:
                switch_result = await self.switch_cluster(cluster)
                if switch_result["status"] != "success":
                    return switch_result
            
            v1 = client.CoreV1Api()
            nodes = v1.list_node()
            
            node_metrics = []
            for node in nodes.items:
                node_info = {
                    "name": node.metadata.name,
                    "cluster": self.current_cluster,
                    "status": "Ready" if any(condition.type == "Ready" and condition.status == "True" 
                                           for condition in node.status.conditions) else "NotReady",
                    "version": node.status.node_info.kubelet_version,
                    "os": f"{node.status.node_info.operating_system} {node.status.node_info.os_image}",
                    "kernel": node.status.node_info.kernel_version,
                    "container_runtime": node.status.node_info.container_runtime_version,
                    "capacity": {
                        "cpu": node.status.capacity.get("cpu", "unknown"),
                        "memory": node.status.capacity.get("memory", "unknown"),
                        "pods": node.status.capacity.get("pods", "unknown")
                    },
                    "allocatable": {
                        "cpu": node.status.allocatable.get("cpu", "unknown"),
                        "memory": node.status.allocatable.get("memory", "unknown"),
                        "pods": node.status.allocatable.get("pods", "unknown")
                    }
                }
                node_metrics.append(node_info)
            
            return {
                "status": "success",
                "cluster": self.current_cluster,
                "node_count": len(node_metrics),
                "nodes": node_metrics
            }
            
        except Exception as e:
            logger.error(f"Failed to get node metrics: {e}")
            return {
                "status": "error",
                "message": str(e),
                "cluster": self.current_cluster
            }
    
    async def get_cluster_health(self, cluster: Optional[str] = None) -> Dict[str, Any]:
        """Get overall cluster health status"""
        try:
            # Switch cluster if specified
            if cluster and cluster != self.current_cluster:
                switch_result = await self.switch_cluster(cluster)
                if switch_result["status"] != "success":
                    return switch_result
            
            # Get node status
            node_metrics = await self.get_node_metrics()
            
            # Get system pods status
            system_pods = await self.get_pods("kube-system")
            
            ready_nodes = len([n for n in node_metrics.get("nodes", []) if n["status"] == "Ready"])
            total_nodes = node_metrics.get("node_count", 0)
            
            running_system_pods = len([p for p in system_pods if p["status"] == "Running"])
            total_system_pods = len(system_pods)
            
            health_score = 100
            if total_nodes > 0:
                health_score *= (ready_nodes / total_nodes)
            if total_system_pods > 0:
                health_score *= (running_system_pods / total_system_pods)
            
            return {
                "status": "success",
                "cluster_name": self.current_cluster,
                "health_score": round(health_score, 2),
                "nodes": {
                    "ready": ready_nodes,
                    "total": total_nodes
                },
                "system_pods": {
                    "running": running_system_pods,
                    "total": total_system_pods
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to get cluster health: {e}")
            return {
                "status": "error",
                "message": str(e),
                "cluster": self.current_cluster
            }