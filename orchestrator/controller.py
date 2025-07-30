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
            
            # Setup group chat
            self._setup_group_chat()
            
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
            max_consecutive_auto_reply=10,
            is_termination_msg=lambda x: x.get("content", "").rstrip().endswith("TERMINATE") or 
                                       x.get("content", "").strip() == "" or
                                       "task completed" in x.get("content", "").lower(),
            code_execution_config={"work_dir": "/tmp", "use_docker": False},
        )
        # Create k8s assistant agent with function calling
        if "k8s-agent" in self.agents:
            k8s_agent = self.agents["k8s-agent"]
            
            # Get function definitions
            functions = k8s_agent.get_function_definitions()
            
            function_map = {}
            for func_def in functions:
                func_name = func_def["name"]
                function_map[func_name] = self._create_agent_function(k8s_agent, func_name)
            
            self.autogen_agents["k8s-assistant"] = AssistantAgent(
                name="k8s-assistant",
                llm_config=self.llm_config,
                system_message="""You are a multi-cluster Kubernetes expert assistant working within the KRATOS system.
                
You have access to the following multi-cluster Kubernetes operations:
- list_clusters: List all available Kubernetes clusters
- switch_cluster: Switch to a different cluster context
- get_pods: List pods in a namespace
- restart_deployment: Restart a deployment
- apply_yaml: Apply Kubernetes manifests
- get_node_metrics: Get cluster node information
- get_cluster_health: Get overall cluster health
- scale_deployment: Scale deployments up or down
- get_logs: Get pod logs

Always provide clear, actionable responses about multi-cluster Kubernetes operations.
When asked to perform operations, use the appropriate function calls.
Format responses in a user-friendly way with relevant details.

Remember to:
1. List available clusters when users ask about cluster operations
2. Ask for clarification if cluster, namespace, or deployment names are not specified
3. Provide status updates during operations
4. Include relevant details in responses (cluster names, pod counts, health scores, etc.)
5. Suggest best practices when appropriate
6. When working with multiple clusters, clearly indicate which cluster you're operating on
7. Always end your response with "TERMINATE" when the task is completed successfully
8. Do not ask follow-up questions unless absolutely necessary for task completion
""",
                function_map=function_map
            )
    
    def _create_agent_function(self, agent: K8sAgent, function_name: str):
        """Create a function wrapper for AutoGen integration"""
        async def agent_function(**kwargs):
            try:
                result = await agent.execute_function(function_name, **kwargs)
                
                # Store in conversation history
                self.conversation_history.append({
                    "timestamp": datetime.utcnow().isoformat(),
                    "agent": agent.name,
                    "function": function_name,
                    "parameters": kwargs,
                    "result": result
                })
                
                return result
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
                
                return error_result
        
        return agent_function
    
    def _setup_group_chat(self):
        """Setup AutoGen group chat"""
        if not self.autogen_agents:
            logger.warning("No AutoGen agents available for group chat")
            return
            
        # Create group chat with all agents
        agents_list = list(self.autogen_agents.values())
        
        self.group_chat = GroupChat(
            agents=agents_list,
            messages=[],
            max_round=self.config.get("max_round", 10),
            speaker_selection_method="auto"
        )
        
        self.group_chat_manager = GroupChatManager(
            groupchat=self.group_chat,
            llm_config=self.llm_config
        )
    
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
            
            # Route to specific agent or use group chat
            if selected_agent and selected_agent in self.autogen_agents:
                result = await self._process_with_specific_agent(message, selected_agent, task_id)
            else:
                result = await self._process_with_group_chat(message, task_id)
            
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
    
    async def _process_with_specific_agent(self, message: str, agent_name: str, task_id: str) -> Dict[str, Any]:
        """Process message with a specific agent"""
        try:
            user_proxy = self.autogen_agents["user"]
            target_agent = self.autogen_agents[agent_name]
            
            # Clear previous messages
            user_proxy.clear_history()
            target_agent.clear_history()
            
            # Initiate chat
            chat_result = user_proxy.initiate_chat(
                target_agent,
                message=message,
                max_turns=3,
                silent=False
            )
            
            return {
                "agent": agent_name,
                "messages": chat_result.chat_history,
                "summary": chat_result.summary if hasattr(chat_result, 'summary') else "Task completed"
            }
            
        except Exception as e:
            logger.error(f"Error in specific agent processing: {e}")
            return {
                "agent": agent_name,
                "error": str(e)
            }
    
    async def _process_with_group_chat(self, message: str, task_id: str) -> Dict[str, Any]:
        """Process message with group chat"""
        try:
            if not self.group_chat_manager:
                return {"error": "Group chat not initialized"}
            
            user_proxy = self.autogen_agents["user"]
            
            # Clear group chat history
            self.group_chat.reset()
            
            # Initiate group chat
            chat_result = user_proxy.initiate_chat(
                self.group_chat_manager,
                message=message,
                max_turns=4
            )
            
            return {
                "type": "group_chat",
                "messages": chat_result.chat_history,
                "summary": chat_result.summary if hasattr(chat_result, 'summary') else "Task completed"
            }
            
        except Exception as e:
            logger.error(f"Error in group chat processing: {e}")
            return {
                "type": "group_chat", 
                "error": str(e)
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