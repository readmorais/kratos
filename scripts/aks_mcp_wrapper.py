"""
AKS MCP Server Wrapper
Provides interface to Azure Kubernetes Service via MCP protocol
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, Any
import httpx
import yaml
from kubernetes import client, config
from azure.identity import DefaultAzureCredential, AzureCliCredential
from azure.mgmt.containerservice import ContainerServiceClient

logger = logging.getLogger(__name__)

class AKSMCPWrapper:
    """Wrapper for AKS MCP server interactions"""
    
    def __init__(self, mcp_endpoint: str, subscription_id: str, resource_group: str, cluster_name: str):
        self.mcp_endpoint = mcp_endpoint.rstrip('/')
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.cluster_name = cluster_name
        self.credential = None
        self.k8s_client = None
        self.aks_client = None
        
    async def initialize(self) -> bool:
        """Initialize Azure credentials and Kubernetes client"""
        try:
            # Try Azure CLI credential first, fallback to default
            try:
                self.credential = AzureCliCredential()
                # Test the credential
                token = self.credential.get_token("https://management.azure.com/.default")
                logger.info("Successfully authenticated with Azure CLI")
            except Exception as e:
                logger.warning(f"Azure CLI authentication failed: {e}")
                self.credential = DefaultAzureCredential()
                logger.info("Using default Azure credential")
            
            # Initialize AKS management client
            self.aks_client = ContainerServiceClient(self.credential, self.subscription_id)
            
            # Get AKS credentials and configure kubectl
            credentials = self.aks_client.managed_clusters.list_cluster_user_credentials(
                self.resource_group, self.cluster_name
            )
            
            if credentials.kubeconfigs:
                kubeconfig = credentials.kubeconfigs[0].value.decode('utf-8')
                config.load_kube_config_from_dict(yaml.safe_load(kubeconfig))
                self.k8s_client = client.ApiClient()
                logger.info("Successfully initialized Kubernetes client")
                return True
            else:
                logger.error("No kubeconfig found for cluster")
                return False
                
        except Exception as e:
            logger.error(f"Failed to initialize AKS MCP wrapper: {e}")
            return False
    
    async def mcp_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Make a request to the MCP server"""
        try:
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
    
    async def get_pods(self, namespace: str = "default") -> List[Dict[str, Any]]:
        """Get pods in a namespace"""
        try:
            v1 = client.CoreV1Api()
            pods = v1.list_namespaced_pod(namespace=namespace)
            
            pod_list = []
            for pod in pods.items:
                pod_info = {
                    "name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
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
            
            logger.info(f"Retrieved {len(pod_list)} pods from namespace {namespace}")
            return pod_list
            
        except Exception as e:
            logger.error(f"Failed to get pods: {e}")
            return []
    
    async def restart_deployment(self, namespace: str, deployment_name: str) -> Dict[str, Any]:
        """Restart a deployment"""
        try:
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
                "timestamp": datetime.datetime.utcnow().isoformat()
            }
            
            logger.info(f"Successfully restarted deployment {deployment_name}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to restart deployment: {e}")
            return {
                "status": "error",
                "message": str(e),
                "deployment": deployment_name,
                "namespace": namespace
            }
    
    async def apply_yaml(self, yaml_content: str) -> Dict[str, Any]:
        """Apply YAML manifest to cluster"""
        try:
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
                        results.append({"resource": f"{kind}/{name}", "action": "created"})
                    except client.ApiException as e:
                        if e.status == 409:  # Already exists
                            apps_v1.patch_namespaced_deployment(name=name, namespace=namespace, body=doc)
                            results.append({"resource": f"{kind}/{name}", "action": "updated"})
                        else:
                            raise
                            
                elif kind == "Service":
                    v1 = client.CoreV1Api()
                    try:
                        v1.create_namespaced_service(namespace=namespace, body=doc)
                        results.append({"resource": f"{kind}/{name}", "action": "created"})
                    except client.ApiException as e:
                        if e.status == 409:
                            v1.patch_namespaced_service(name=name, namespace=namespace, body=doc)
                            results.append({"resource": f"{kind}/{name}", "action": "updated"})
                        else:
                            raise
            
            return {
                "status": "success",
                "message": f"Applied {len(results)} resources",
                "results": results
            }
            
        except Exception as e:
            logger.error(f"Failed to apply YAML: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    async def get_node_metrics(self) -> Dict[str, Any]:
        """Get node metrics and health information"""
        try:
            v1 = client.CoreV1Api()
            nodes = v1.list_node()
            
            node_metrics = []
            for node in nodes.items:
                node_info = {
                    "name": node.metadata.name,
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
                "node_count": len(node_metrics),
                "nodes": node_metrics
            }
            
        except Exception as e:
            logger.error(f"Failed to get node metrics: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    async def get_cluster_health(self) -> Dict[str, Any]:
        """Get overall cluster health status"""
        try:
            # Get cluster info
            cluster_info = self.aks_client.managed_clusters.get(
                self.resource_group, 
                self.cluster_name
            )
            
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
                "cluster_name": self.cluster_name,
                "cluster_status": cluster_info.provisioning_state,
                "kubernetes_version": cluster_info.kubernetes_version,
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
                "message": str(e)
            }