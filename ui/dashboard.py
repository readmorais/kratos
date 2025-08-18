"""
KRATOS Streamlit Dashboard
Web interface for multi-agent Kubernetes operations
"""

import streamlit as st
import asyncio
import json
import yaml
import logging
from datetime import datetime
from typing import Dict, Any, Optional
import os
import sys
import threading
import time
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestrator.controller import KratosController

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page configuration
st.set_page_config(
    page_title="KRATOS Dashboard",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        text-align: center;
        color: #1f77b4;
        font-size: 3rem;
        font-weight: bold;
        margin-bottom: 2rem;
    }
    
    .agent-card {
        border: 1px solid #ddd;
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
        background-color: #f8f9fa;
    }
    
    .status-success {
        color: #28a745;
        font-weight: bold;
    }
    
    .status-error {
        color: #dc3545;
        font-weight: bold;
    }
    
    .status-warning {
        color: #ffc107;
        font-weight: bold;
    }
    
    .function-card {
        border-left: 4px solid #1f77b4;
        padding: 0.5rem;
        margin: 0.25rem 0;
        background-color: #f0f8ff;
    }
    
    .conversation-message {
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
        background-color: transparent;
    }
    
    .user-message {
        border-left: 4px solid #2196f3;
    }
    
    .assistant-message {
        border-left: 4px solid #9c27b0;
    }
    
    .system-message {
        border-left: 4px solid #ff9800;
    }
</style>
""", unsafe_allow_html=True)

class KratosDashboard:
    """Main dashboard class for KRATOS"""
    
    def __init__(self):
        self.controller = None
        self.initialized = False
        
    async def initialize_controller(self) -> bool:
        """Initialize the KRATOS controller"""
        try:
            # Load configuration
            config = self._load_config()
            
            # Initialize controller
            self.controller = KratosController(config)
            self.initialized = await self.controller.initialize()
            
            return self.initialized
            
        except Exception as e:
            logger.error(f"Failed to initialize controller: {e}")
            st.error(f"Failed to initialize KRATOS: {e}")
            return False
    
    def _load_config(self) -> Dict[str, Any]:
        """Load KRATOS configuration"""
        # Load environment variables from .env file
        load_dotenv()
        
        config = {
            # Azure OpenAI configuration
            "azure_openai_api_key": os.getenv("AZURE_OPENAI_API_KEY", ""),
            "azure_openai_endpoint": os.getenv("AZURE_OPENAI_ENDPOINT", ""),
            "azure_openai_api_version": os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
            "azure_openai_deployment_name": os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4"),
            "temperature": float(os.getenv("AUTOGEN_TEMPERATURE", "0.1")),
            "timeout": int(os.getenv("AUTOGEN_TIMEOUT", "120")),
            "max_round": int(os.getenv("AUTOGEN_MAX_ROUND", "10")),
            
            # Agent configurations
            "agents": {
                "k8s-agent": {
                    "mcp_endpoint": os.getenv("AKS_MCP_ENDPOINT", "http://localhost:3000")
                }
            }
        }
        
        return config
    
    def render_header(self):
        """Render the dashboard header"""
        st.markdown('<div class="main-header">⚡ KRATOS</div>', unsafe_allow_html=True)
        st.markdown('<div style="text-align: center; color: #666; font-size: 1.2rem; margin-bottom: 2rem;">Kubernetes Runtime Agentic Operating System</div>', unsafe_allow_html=True)
        
        # Status indicators
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if self.initialized:
                st.success("🟢 Controller Online")
            else:
                st.error("🔴 Controller Offline")
        
        with col2:
            if self.controller and self.controller.agents:
                agent_count = len(self.controller.agents)
                st.info(f"🤖 {agent_count} Agent{'s' if agent_count != 1 else ''} Active")
            else:
                st.warning("🤖 0 Agents Active")
        
        with col3:
            if self.controller:
                status = self.controller.get_agent_status()
                running_tasks = status.get("running_tasks", 0)
                if running_tasks > 0:
                    st.warning(f"⚙️ {running_tasks} Task{'s' if running_tasks != 1 else ''} Running")
                else:
                    st.success("⚙️ Ready")
            else:
                st.info("⚙️ Standby")
        
        with col4:
            if self.controller and self.controller.agents.get("k8s-agent"):
                k8s_agent = self.controller.agents["k8s-agent"]
                if hasattr(k8s_agent, 'mcp_wrapper') and k8s_agent.mcp_wrapper:
                    current_cluster = k8s_agent.mcp_wrapper.current_cluster
                    if current_cluster:
                        st.info(f"🎯 {current_cluster}")
                    else:
                        st.warning("🎯 No Cluster")
                else:
                    st.warning("🎯 Not Connected")
            else:
                current_time = datetime.now().strftime("%H:%M:%S")
                st.info(f"🕒 {current_time}")
    
    def render_sidebar(self):
        """Render the sidebar with agent information"""
        with st.sidebar:
            st.header("🎛️ Control Panel")
            
            # Settings section (collapsible)
            with st.expander("⚙️ Settings", expanded=False):
                # Environment check
                env_vars = [
                    ("AKS_MCP_ENDPOINT", "MCP Server Endpoint"),
                    ("AZURE_OPENAI_API_KEY", "Azure OpenAI API Key"),
                    ("AZURE_OPENAI_ENDPOINT", "Azure OpenAI Endpoint"),
                    ("AZURE_OPENAI_DEPLOYMENT_NAME", "Azure OpenAI Deployment")
                ]
                
                for var, description in env_vars:
                    value = os.getenv(var, "")
                    if value:
                        st.success(f"✅ {description}")
                    else:
                        st.error(f"❌ {description}")
                        st.caption(f"Set {var} in .env file")
            
            # Agent status
            if self.controller:
                status = self.controller.get_agent_status()
                
                st.subheader("🤖 Agents")
                for agent_name, agent_info in status.get("agents", {}).items():
                    with st.expander(f"{agent_name}", expanded=False):
                        if agent_info.get("initialized", False):
                            st.success("Status: Online")
                        else:
                            st.error("Status: Offline")
                        
                        # Show cluster information for k8s-agent
                        if agent_name == "k8s-agent" and "cluster_info" in agent_info:
                            cluster_info = agent_info["cluster_info"]
                            st.write("**Current Cluster:**", cluster_info.get("current_cluster", "None"))
                            
                            available_clusters = cluster_info.get("available_clusters", [])
                            if available_clusters:
                                st.write("**Available Clusters:**")
                                for cluster in available_clusters:
                                    st.write(f"• {cluster}")
                            else:
                                st.write("**Available Clusters:** None configured")
                        
                        st.write("**Capabilities:**")
                        for cap in agent_info.get("capabilities", []):
                            st.write(f"• {cap}")
                
                # Available functions
                st.subheader("⚡ Functions")
                functions = self.controller.get_available_functions()
                for agent_name, func_list in functions.items():
                    with st.expander(f"{agent_name} Functions", expanded=False):
                        for func in func_list:
                            st.markdown(f"""
                            <div class="function-card">
                                <strong>{func['name']}</strong><br>
                                <small>{func['description']}</small>
                            </div>
                            """, unsafe_allow_html=True)
    
    def render_task_interface(self):
        """Render the main task interface"""
        st.header("🚀 Task Execution")
        
        # Task creation form
        with st.container():
            col1, col2 = st.columns([2, 1])
            
            with col1:
                # Message input
                user_message = st.text_area(
                    "Enter your multi-cluster Kubernetes task:",
                    placeholder="e.g., 'List all available clusters' or 'Show me all pods in the default namespace' or 'Restart the nginx deployment in staging on cluster-prod'",
                    height=100,
                    help="Describe what you want to do with your Kubernetes clusters"
                )
            
            with col2:
                st.write("**Agent Selection:**")
                
                # Agent selection
                if self.controller and self.controller.autogen_agents:
                    agent_options = ["Auto-select"] + list(self.controller.autogen_agents.keys())
                    selected_agent = st.selectbox(
                        "Choose agent:",
                        agent_options,
                        index=0,
                        help="Select a specific agent or let the system choose automatically"
                    )
                    
                    if selected_agent == "Auto-select":
                        selected_agent = None
                else:
                    st.warning("No agents available")
                    selected_agent = None
                
                # Execute button
                execute_button = st.button(
                    "🚀 Execute Task",
                    type="primary",
                    disabled=not (self.initialized and user_message.strip()),
                    help="Execute the task with the selected agent"
                )
        
        # Execute task
        if execute_button and user_message.strip():
            self._execute_task_sync(user_message, selected_agent)
    
    def _execute_task_sync(self, message: str, selected_agent: Optional[str]):
        """Execute task synchronously for Streamlit"""
        with st.spinner("🔄 Processing task..."):
            try:
                # Run the async task in a thread
                result = self._run_async_task(message, selected_agent)
                
                if result.get("status") == "success":
                    st.success("✅ Task completed successfully!")
                    
                    # Display results
                    task_result = result.get("result", {})
                    
                    # Show conversation
                    if "messages" in task_result:
                        messages = task_result["messages"]
                        logger.info(f"Displaying {len(messages)} messages in UI")
                        if messages:
                            self._display_conversation(messages)
                        else:
                            st.warning("Task completed but no conversation messages to display")
                            logger.warning("No messages to display in UI")
                    
                    # Show summary
                    if "summary" in task_result:
                        st.info(f"📋 **Summary:** {task_result['summary']}")
                    
                    # Show function execution history
                    history = result.get("conversation_history", [])
                    logger.info(f"Function execution history: {len(history)} entries")
                    if history:
                        st.subheader("🔧 Function Execution Results")
                        for entry in history[-3:]:  # Show last 3 function calls
                            if entry['result'].get('status') == 'success':
                                st.success(f"✅ **{entry['function']}**: {entry['result'].get('message', 'Success')}")
                            else:
                                st.error(f"❌ **{entry['function']}**: {entry['result'].get('message', 'Error')}")
                        
                        with st.expander("🔍 Function Execution Details", expanded=False):
                            for entry in history[-3:]:  # Show last 3 function calls
                                st.json({
                                    "function": entry['function'],
                                    "parameters": entry['parameters'],
                                    "result": entry['result'],
                                    "timestamp": entry['timestamp']
                                })
                    
                    # Show raw result for debugging
                    with st.expander("🔍 Raw Result", expanded=False):
                        st.json(task_result)
                    
                    # Force refresh of sidebar to update cluster info
                    st.rerun()
                
                else:
                    st.error(f"❌ Task failed: {result.get('message', 'Unknown error')}")
                    
            except Exception as e:
                st.error(f"❌ Error executing task: {e}")
                logger.error(f"Task execution error: {e}")
    
    def _run_async_task(self, message: str, selected_agent: Optional[str]) -> Dict[str, Any]:
        """Run async task in a separate thread"""
        result = {}
        exception = None
        
        def run_task():
            nonlocal result, exception
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(
                    self.controller.process_user_message(message, selected_agent)
                )
                loop.close()
            except Exception as e:
                exception = e
        
        thread = threading.Thread(target=run_task)
        thread.start()
        thread.join(timeout=120)  # 2 minute timeout
        
        if thread.is_alive():
            return {"status": "error", "message": "Task timed out"}
        
        if exception:
            raise exception
            
        return result
    
    async def _execute_task(self, message: str, selected_agent: Optional[str]):
        """Execute a task and display results"""
        with st.spinner("🔄 Processing task..."):
            try:
                # Process the message
                result = await self.controller.process_user_message(message, selected_agent)
                
                if result.get("status") == "success":
                    st.success("✅ Task completed successfully!")
                    
                    # Display results
                    task_result = result.get("result", {})
                    
                    # Show conversation
                    if "messages" in task_result:
                        self._display_conversation(task_result["messages"])
                    
                    # Show summary
                    if "summary" in task_result:
                        st.info(f"📋 **Summary:** {task_result['summary']}")
                    
                    # Show raw result for debugging
                    with st.expander("🔍 Raw Result", expanded=False):
                        st.json(task_result)
                
                else:
                    st.error(f"❌ Task failed: {result.get('message', 'Unknown error')}")
                    
            except Exception as e:
                st.error(f"❌ Error executing task: {e}")
                logger.error(f"Task execution error: {e}")
    
    def _display_conversation(self, messages: list):
        """Display conversation messages"""
        st.subheader("💬 Conversation")
        
        for i, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            name = msg.get("name", role)
            
            # Log message for debugging
            logger.info(f"Displaying message {i}: role={role}, name={name}, content_length={len(content)}")
            
            # Skip empty messages
            if not content or str(content).strip() == "":
                logger.info(f"Skipping empty message {i}")
                continue
            
            # Convert content to string if it's not already
            content_str = str(content)
            
            if role == "user":
                st.markdown(f"""
                <div class="conversation-message user-message">
                    <strong>👤 User:</strong><br>
                    {content_str}
                </div>
                """, unsafe_allow_html=True)
            
            elif role == "assistant":
                st.markdown(f"""
                <div class="conversation-message assistant-message">
                    <strong>🤖 {name}:</strong><br>
                    {content_str}
                </div>
                """, unsafe_allow_html=True)
            
            else:
                st.markdown(f"""
                <div class="conversation-message system-message">
                    <strong>⚙️ System:</strong><br>
                    {content_str}
                </div>
                """, unsafe_allow_html=True)
    
    def render_history(self):
        """Render conversation history"""
        st.header("📚 History")
        
        if self.controller:
            history = self.controller.get_recent_history(20)
            
            if history:
                for entry in reversed(history):  # Show most recent first
                    with st.expander(f"🕒 {entry['timestamp']} - {entry['function']}", expanded=False):
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.write("**Parameters:**")
                            st.json(entry.get("parameters", {}))
                        
                        with col2:
                            st.write("**Result:**")
                            result = entry.get("result", {})
                            if result.get("status") == "success":
                                st.success("✅ Success")
                            else:
                                st.error("❌ Error")
                            st.json(result)
            else:
                st.info("No history available yet. Execute some tasks to see history here.")
        else:
            st.warning("Controller not initialized")

# Main dashboard instance
dashboard = KratosDashboard()

def main():
    """Main dashboard application"""
    # Initialize controller if not done
    if not dashboard.initialized:
        with st.spinner("🔄 Initializing KRATOS..."):
            # Run initialization in a thread
            def init_controller():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(dashboard.initialize_controller())
                loop.close()
                return result
            
            init_thread = threading.Thread(target=init_controller)
            init_thread.start()
            init_thread.join()
    
    # Render dashboard
    dashboard.render_header()
    dashboard.render_sidebar()
    
    # Main content tabs
    tab1, tab2, tab3 = st.tabs(["🚀 Tasks", "📊 Monitoring", "📚 History"])
    
    with tab1:
        dashboard.render_task_interface()
    
    with tab2:
        st.header("📊 Cluster Monitoring")
        
        if dashboard.initialized and dashboard.controller:
            # Cluster selection for monitoring
            k8s_agent = dashboard.controller.agents.get("k8s-agent")
            if k8s_agent and hasattr(k8s_agent, 'mcp_wrapper') and k8s_agent.mcp_wrapper:
                available_clusters = list(k8s_agent.mcp_wrapper.clusters.keys())
                if available_clusters:
                    selected_cluster = st.selectbox(
                        "Select cluster to monitor:",
                        available_clusters,
                        index=available_clusters.index(k8s_agent.mcp_wrapper.current_cluster) if k8s_agent.mcp_wrapper.current_cluster in available_clusters else 0
                    )
                else:
                    st.warning("No clusters available for monitoring")
                    selected_cluster = None
            else:
                selected_cluster = None
            
            # Quick health check
            if st.button("🔍 Check Cluster Health") and selected_cluster:
                with st.spinner("Checking cluster health..."):
                    def check_health():
                        try:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            health = loop.run_until_complete(k8s_agent.get_cluster_health(selected_cluster))
                            loop.close()
                            return health
                        except Exception as e:
                            return {"status": "error", "message": str(e)}
                    
                    health = check_health()
                    
                    if health.get("status") == "success":
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            st.metric(
                                "Health Score", 
                                f"{health.get('health_score', 0)}%"
                            )
                        
                        with col2:
                            nodes = health.get("nodes", {})
                            st.metric(
                                "Ready Nodes",
                                f"{nodes.get('ready', 0)}/{nodes.get('total', 0)}"
                            )
                        
                        with col3:
                            pods = health.get("system_pods", {})
                            st.metric(
                                "System Pods",
                                f"{pods.get('running', 0)}/{pods.get('total', 0)}"
                            )
                        
                        st.json(health)
                    else:
                        st.error(f"Health check failed: {health.get('message', 'Unknown error')}")
                            
        else:
            st.warning("KRATOS not initialized. Cannot perform monitoring.")
    
    with tab3:
        dashboard.render_history()

# Run the dashboard
if __name__ == "__main__":
    main()