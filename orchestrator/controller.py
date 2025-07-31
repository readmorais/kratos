"""
KRATOS Orchestrator Controller
Manages AutoGen conversations and agent coordination
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional
import json
import yaml
from datetime import datetime

import autogen
from autogen import AssistantAgent, UserProxyAgent, GroupChatManager, GroupChat

from agents.k8s_agent import K8sAgent

logger = logging.getLogger(__name__)

class KratosController:
    """Main controller for KRATOS multi-agent system"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.agents = {}
        self.autogen_agents = {}
        self.group_chat = None
        self.group_chat_manager = None
        self.conversation_history = []
        self.task_queue = asyncio.Queue()
        self.running_tasks = {}
        
        # Validate required configuration
        required_config = [
            "azure_openai_api_key",
            "azure_openai_endpoint"
        ]
        
        for key in required_config:
            if not config.get(key):
                raise ValueError(f"Missing required configuration: {key}")
        
        # Validate URLs
        endpoint = config.get("azure_openai_endpoint", "")
        if not endpoint or endpoint in ["", "http://", "https://"]:
            raise ValueError(f"Invalid Azure OpenAI endpoint: {endpoint}. Example: https://your-resource-name.openai.azure.com")
        
        # AutoGen configuration
        self.llm_config = {
            "config_list": [
                {
                    "model": config.get("azure_openai_deployment_name", "gpt-4"),
                    "api_type": "azure", 
                    "api_key": config.get("azure_openai_api_key"),
                    "base_url": config.get("azure_openai_endpoint"),
                    "api_version": config.get("azure_openai_api_version", "2024-02-15-preview"),
                }
            ],
            "temperature": config.get("temperature", 0.1),
            "timeout": config.get("timeout", 120),
        }
        
    async def initialize(self) -> bool:
        """Initialize the controller and all agents"""
        try:
            # Load agent configurations
            agents_config = self.config.get("agents", {})
            
            # Initialize k8s-agent
            if "k8s-agent" in agents_config:
                k8s_config = agents_config["k8s-agent"]
                k8s_agent = K8sAgent(k8s_config)
                
                if await k8s_agent.initialize():
                    self.agents["k8s-agent"] = k8s_agent
                    logger.info("K8s agent initialized successfully")
                else:
                    logger.error("Failed to initialize k8s agent")
                    return False
            
            # Create AutoGen agents
            await self._create_autogen_agents()
            
            logger.info("KRATOS Controller initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize KRATOS Controller: {e}")
            return False
    
    async def _create_autogen_agents(self):
        """Create AutoGen agents with function bindings"""
        
        # Create user proxy agent
        self.autogen_agents["user"] = UserProxyAgent(
            name="user",
            human_input_mode="NEVER",
            max_consecutive_auto_reply=0,
            is_termination_msg=lambda x: True,  # Always terminate after first response
            code_execution_config=False,
        )
        
        # Create k8s assistant agent
        if "k8s-agent" in self.agents:
            k8s_agent = self.agents["k8s-agent"]
            
            # Get function definitions
            functions = k8s_agent.get_function_definitions()
            
            # Create function map for AutoGen
            function_map = {}
            for func_def in functions:
                func_name = func_def["name"]
                function_map[func_name] = self._create_agent_function_wrapper(k8s_agent, func_name)
            
            self.autogen_agents["k8s-assistant"] = AssistantAgent(
                name="k8s-assistant",
                llm_config=self.llm_config,
                system_message="""You are a Kubernetes expert assistant. You have access to these functions:

- list_clusters: List all available clusters
- switch_cluster: Switch to a different cluster (parameter: cluster_name)
- get_pods: Get pods in a namespace (parameters: namespace, cluster)
- restart_deployment: Restart a deployment (parameters: deployment_name, namespace, cluster)
- apply_yaml: Apply YAML manifest (parameters: yaml_content, cluster)
- get_node_metrics: Get node information (parameter: cluster)
- get_cluster_health: Get cluster health (parameter: cluster)
- scale_deployment: Scale deployment (parameters: deployment_name, replicas, namespace, cluster)
- get_logs: Get pod logs (parameters: pod_name, namespace, container_name, tail_lines, cluster)

When users ask for operations:
1. Use the appropriate functions to complete the task
2. Provide clear, helpful responses about what you found or did
3. Always end your response with "TERMINATE" when the task is complete

For searching across all namespaces, use namespace="all" in get_pods function.
""",
                function_map=function_map
            )
    
    def _create_agent_function_wrapper(self, agent: K8sAgent, function_name: str):
        """Create a function wrapper for AutoGen integration"""
        def sync_wrapper(**kwargs):
            """Synchronous wrapper for async agent functions"""
            try:
                # Run the async function
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(agent.execute_function(function_name, **kwargs))
                loop.close()
                
                # Store in conversation history
                self.conversation_history.append({
                    "timestamp": datetime.utcnow().isoformat(),
                    "agent": agent.name,
                    "function": function_name,
                    "parameters": kwargs,
                    "result": result
                })
                
                # Return formatted result for AutoGen
                if result.get("status") == "success":
                    if function_name == "list_clusters":
                        clusters = result.get("clusters", [])
                        return f"Available clusters: {', '.join([c['name'] for c in clusters])}"
                    
                    elif function_name == "switch_cluster":
                        return f"Successfully switched to cluster: {result.get('cluster', 'unknown')}"
                    
                    elif function_name == "get_pods":
                        pods = result.get("pods", [])
                        if not pods:
                            return f"No pods found in namespace {kwargs.get('namespace', 'default')}"
                        
                        pod_info = []
                        for pod in pods:
                            status = pod.get("status", "Unknown")
                            name = pod.get("name", "Unknown")
                            namespace = pod.get("namespace", "Unknown")
                            pod_info.append(f"  - {name} ({status}) in {namespace}")
                        
                        return f"Found {len(pods)} pods:\n" + "\n".join(pod_info)
                    
                    elif function_name == "restart_deployment":
                        return f"Successfully restarted deployment: {result.get('deployment', 'unknown')}"
                    
                    elif function_name == "get_cluster_health":
                        health_score = result.get("health_score", 0)
                        nodes = result.get("nodes", {})
                        return f"Cluster health: {health_score}% - {nodes.get('ready', 0)}/{nodes.get('total', 0)} nodes ready"
                    
                    else:
                        return f"Function {function_name} completed successfully: {result.get('message', 'No details')}"
                else:
                    return f"Error in {function_name}: {result.get('message', 'Unknown error')}"
                    
            except Exception as e:
                error_result = {
                    "status": "error",
                    "message": str(e),
                    "agent": agent.name,
                    "function": function_name
                }
                
                self.conversation_history.append({
                    "timestamp": datetime.utcnow().isoformat(),
                    "agent": agent.name, 
                    "function": function_name,
                    "parameters": kwargs,
                    "result": error_result
                })
                
                return f"Error executing {function_name}: {str(e)}"
        
        return sync_wrapper
    
    async def process_user_message(self, message: str, selected_agent: Optional[str] = None) -> Dict[str, Any]:
        """Process a user message through the agent system"""
        try:
            task_id = f"task_{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}"
            
            # Store task start
            task_info = {
                "id": task_id,
                "message": message,
                "selected_agent": selected_agent,
                "start_time": datetime.utcnow().isoformat(),
                "status": "processing"
            }
            
            self.running_tasks[task_id] = task_info
            
            # Use direct communication with k8s-assistant
            result = await self._process_with_k8s_assistant(message, task_id)
            
            # Update task completion
            task_info.update({
                "status": "completed",
                "end_time": datetime.utcnow().isoformat(),
                "result": result
            })
            
            return {
                "task_id": task_id,
                "status": "success",
                "result": result,
                "conversation_history": self.get_recent_history(10)
            }
            
        except Exception as e:
            logger.error(f"Error processing user message: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
        finally:
            # Clean up completed task
            if task_id in self.running_tasks:
                self.running_tasks[task_id]["status"] = "completed"
    
    async def _process_with_k8s_assistant(self, message: str, task_id: str) -> Dict[str, Any]:
        """Process message directly with k8s assistant"""
        try:
            user_proxy = self.autogen_agents["user"]
            k8s_assistant = self.autogen_agents["k8s-assistant"]
            
            # Clear previous messages
            user_proxy.clear_history()
            k8s_assistant.clear_history()
            
            # Initiate direct chat
            chat_result = user_proxy.initiate_chat(
                k8s_assistant,
                message=message,
                max_turns=1,
                silent=False
            )
            
            return {
                "agent": "k8s-assistant",
                "messages": chat_result.chat_history if hasattr(chat_result, 'chat_history') else [],
                "summary": chat_result.summary if hasattr(chat_result, 'summary') else "Task completed"
            }
            
        except Exception as e:
            logger.error(f"Error in k8s assistant processing: {e}")
            return {
                "agent": "k8s-assistant",
                "error": str(e),
                "messages": []
            }
    
    def get_recent_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent conversation history"""
        return self.conversation_history[-limit:] if self.conversation_history else []
    
    def get_agent_status(self) -> Dict[str, Any]:
        """Get status of all agents"""
        status = {}
        for name, agent in self.agents.items():
            if hasattr(agent, 'get_status'):
                status[name] = agent.get_status()
            else:
                status[name] = {"name": name, "type": "unknown"}
        
        return {
            "agents": status,
            "autogen_agents": list(self.autogen_agents.keys()),
            "running_tasks": len([t for t in self.running_tasks.values() if t["status"] == "processing"]),
            "total_conversations": len(self.conversation_history)
        }
    
    def get_available_functions(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get available functions for each agent"""
        functions = {}
        for name, agent in self.agents.items():
            if hasattr(agent, 'get_function_definitions'):
                functions[name] = agent.get_function_definitions()
        return functions

    async def shutdown(self):
        """Gracefully shutdown the controller"""
        logger.info("Shutting down KRATOS Controller")
        
        # Cancel running tasks
        for task_id, task_info in self.running_tasks.items():
            if task_info["status"] == "processing":
                task_info["status"] = "cancelled"
        
        # Clear agents
        self.agents.clear()
        self.autogen_agents.clear()
        
        logger.info("KRATOS Controller shutdown complete")