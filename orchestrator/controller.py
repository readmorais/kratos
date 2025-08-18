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
from autogen import AssistantAgent, UserProxyAgent

from agents.k8s_agent import K8sAgent

logger = logging.getLogger(__name__)

class KratosController:
    """Main controller for KRATOS multi-agent system"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.agents = {}
        self.autogen_agents = {}
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
        if not endpoint or endpoint in ["", "http://", "https://", "http://localhost", "https://localhost"]:
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
        
        # Create user proxy agent - no auto reply, terminates immediately
        self.autogen_agents["user"] = UserProxyAgent(
            name="user",
            human_input_mode="NEVER",
            max_consecutive_auto_reply=0,
            is_termination_msg=lambda x: True,
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
                system_message="""You are a Kubernetes expert assistant managing multiple clusters. You have access to these functions:

- list_clusters: List all available clusters
- switch_cluster: Switch to a different cluster (parameter: cluster_name)
- get_pods: Get pods in a namespace (parameters: namespace, cluster) - use namespace="all" to search all namespaces
- restart_deployment: Restart a deployment (parameters: deployment_name, namespace, cluster)
- apply_yaml: Apply YAML manifest (parameters: yaml_content, cluster)
- get_node_metrics: Get node information (parameter: cluster)
- get_cluster_health: Get cluster health (parameter: cluster)
- scale_deployment: Scale deployment (parameters: deployment_name, replicas, namespace, cluster)
- get_logs: Get pod logs (parameters: pod_name, namespace, container_name, tail_lines, cluster)

When users ask for operations:
1. Execute the appropriate functions to complete the task
2. Always call functions when needed - don't just describe what you would do
3. For searching across namespaces, use namespace="all"
4. Provide clear, helpful responses about what you found or did
5. Always end your response with "TERMINATE" when the task is complete

Example: If asked to "switch to minerva cluster and look for microbot across all namespaces":
1. Call switch_cluster with cluster_name="minerva"
2. Call get_pods with namespace="all" to search all namespaces
3. Filter results for pods containing "microbot"
4. Report findings and end with "TERMINATE"
""",
                function_map=function_map
            )
    
    def _create_agent_function_wrapper(self, agent: K8sAgent, function_name: str):
        """Create a function wrapper for AutoGen integration"""
        def sync_wrapper(**kwargs):
            """Synchronous wrapper for async agent functions"""
            try:
                logger.info(f"Executing function {function_name} with args: {kwargs}")
                
                # Run the async function
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(agent.execute_function(function_name, **kwargs))
                loop.close()
                
                logger.info(f"Function {function_name} result: {result}")
                
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
                        if clusters:
                            cluster_names = [c.get('name', str(c)) for c in clusters]
                            return f"Available clusters: {', '.join(cluster_names)}"
                        else:
                            return "No clusters found"
                    
                    elif function_name == "switch_cluster":
                        cluster = result.get("cluster", kwargs.get("cluster_name", "unknown"))
                        return f"Successfully switched to cluster: {cluster}"
                    
                    elif function_name == "get_pods":
                        pods = result.get("pods", [])
                        namespace = kwargs.get("namespace", "default")
                        
                        if not pods:
                            return f"No pods found in namespace {namespace}"
                        
                        # Filter for microbot if searching across all namespaces
                        if "microbot" in str(kwargs).lower() or namespace == "all":
                            microbot_pods = [pod for pod in pods if "microbot" in pod.get("name", "").lower()]
                            if microbot_pods:
                                pod_info = []
                                for pod in microbot_pods:
                                    status = pod.get("status", "Unknown")
                                    name = pod.get("name", "Unknown")
                                    ns = pod.get("namespace", "Unknown")
                                    pod_info.append(f"  - {name} ({status}) in namespace {ns}")
                                return f"Found {len(microbot_pods)} microbot pods:\n" + "\n".join(pod_info)
                            else:
                                return "No microbot pods found across all namespaces"
                        else:
                            pod_info = []
                            for pod in pods[:10]:  # Limit to first 10 pods
                                status = pod.get("status", "Unknown")
                                name = pod.get("name", "Unknown")
                                ns = pod.get("namespace", "Unknown")
                                pod_info.append(f"  - {name} ({status}) in {ns}")
                            
                            more_text = f" (showing first 10 of {len(pods)})" if len(pods) > 10 else ""
                            return f"Found {len(pods)} pods{more_text}:\n" + "\n".join(pod_info)
                    
                    elif function_name == "restart_deployment":
                        deployment = result.get("deployment", kwargs.get("deployment_name", "unknown"))
                        return f"Successfully restarted deployment: {deployment}"
                    
                    elif function_name == "get_cluster_health":
                        health_score = result.get("health_score", 0)
                        nodes = result.get("nodes", {})
                        cluster = result.get("cluster_name", "unknown")
                        return f"Cluster {cluster} health: {health_score}% - {nodes.get('ready', 0)}/{nodes.get('total', 0)} nodes ready"
                    
                    else:
                        return f"Function {function_name} completed successfully: {result.get('message', 'No details')}"
                else:
                    error_msg = result.get('message', 'Unknown error')
                    return f"Error in {function_name}: {error_msg}"
                    
            except Exception as e:
                logger.error(f"Error executing function {function_name}: {e}")
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
            
            logger.info(f"Starting conversation with message: {message}")
            
            # Initiate direct chat with single turn
            chat_result = user_proxy.initiate_chat(
                k8s_assistant,
                message=message,
                max_turns=1,
                silent=False
            )
            
            logger.info(f"Chat completed, result type: {type(chat_result)}")
            
            # Extract messages from chat result
            messages = []
            if hasattr(chat_result, 'chat_history'):
                messages = chat_result.chat_history
            elif hasattr(chat_result, 'messages'):
                messages = chat_result.messages
            else:
                # Fallback - get from agent histories
                messages = user_proxy.chat_messages.get(k8s_assistant, [])
            
            logger.info(f"Extracted {len(messages)} messages")
            
            return {
                "agent": "k8s-assistant",
                "messages": messages,
                "summary": getattr(chat_result, 'summary', "Task completed"),
                "task_id": task_id
            }
            
        except Exception as e:
            logger.error(f"Error in k8s assistant processing: {e}")
            return {
                "agent": "k8s-assistant",
                "error": str(e),
                "messages": [],
                "task_id": task_id
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