#!/usr/bin/env python3
"""
KRATOS - Kubernetes Runtime Agentic Operating System
Main entry point for the multi-agent system
"""

import asyncio
import logging
import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv

# Add current directory to path
sys.path.append(str(Path(__file__).parent))

from orchestrator.controller import KratosController

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('kratos.log')
    ]
)
logger = logging.getLogger(__name__)

def load_configuration() -> dict:
    """Load KRATOS configuration from environment and config files"""
    
    # Load environment variables
    load_dotenv()
    
    config = {
        # System configuration
        "version": "1.0.0",
        "environment": os.getenv("KRATOS_ENV", "development"),
        
        # AutoGen/LLM configuration
        "model": os.getenv("OPENAI_MODEL", "gpt-4"),
        "api_key": os.getenv("OPENAI_API_KEY", ""),
        "base_url": os.getenv("OPENAI_BASE_URL", ""),
        "temperature": float(os.getenv("AUTOGEN_TEMPERATURE", "0.1")),
        "timeout": int(os.getenv("AUTOGEN_TIMEOUT", "120")),
        "max_round": int(os.getenv("AUTOGEN_MAX_ROUND", "10")),
        
        # Azure configuration
        "azure": {
            "subscription_id": os.getenv("AZURE_SUBSCRIPTION_ID", ""),
            "tenant_id": os.getenv("AZURE_TENANT_ID", ""),
            "client_id": os.getenv("AZURE_CLIENT_ID", ""),
            "client_secret": os.getenv("AZURE_CLIENT_SECRET", ""),
            "resource_group": os.getenv("AZURE_RESOURCE_GROUP", ""),
            "cluster_name": os.getenv("AZURE_AKS_CLUSTER_NAME", ""),
        },
        
        # MCP configuration
        "mcp": {
            "server_host": os.getenv("MCP_SERVER_HOST", "localhost"),
            "server_port": int(os.getenv("MCP_SERVER_PORT", "8080")),
            "aks_endpoint": os.getenv("AKS_MCP_ENDPOINT", "http://localhost:3000"),
        },
        
        # Agent configurations
        "agents": {
            "k8s-agent": {
                "mcp_endpoint": os.getenv("AKS_MCP_ENDPOINT", "http://localhost:3000"),
                "subscription_id": os.getenv("AZURE_SUBSCRIPTION_ID", ""),
                "resource_group": os.getenv("AZURE_RESOURCE_GROUP", ""),
                "cluster_name": os.getenv("AZURE_AKS_CLUSTER_NAME", ""),
                "timeout": int(os.getenv("AGENT_TIMEOUT", "300")),
                "retry_attempts": int(os.getenv("AGENT_RETRY_ATTEMPTS", "3")),
            }
        },
        
        # Logging configuration
        "logging": {
            "level": os.getenv("LOG_LEVEL", "INFO"),
            "format": os.getenv("LOG_FORMAT", "text"),
        }
    }
    
    return config

async def run_cli_mode(controller: KratosController):
    """Run KRATOS in CLI interactive mode"""
    logger.info("🚀 Starting KRATOS CLI mode")
    logger.info("Type 'help' for available commands, 'quit' to exit")
    
    while True:
        try:
            # Get user input
            user_input = input("\nKRATOS> ").strip()
            
            if not user_input:
                continue
            
            # Handle system commands
            if user_input.lower() in ['quit', 'exit', 'q']:
                logger.info("Shutting down KRATOS...")
                break
            elif user_input.lower() == 'help':
                print_help()
                continue
            elif user_input.lower() == 'status':
                status = controller.get_agent_status()
                print(f"\n📊 KRATOS Status:")
                print(f"  Agents: {len(status.get('agents', {}))}")
                print(f"  AutoGen Agents: {len(status.get('autogen_agents', []))}")
                print(f"  Running Tasks: {status.get('running_tasks', 0)}")
                print(f"  Total Conversations: {status.get('total_conversations', 0)}")
                continue
            elif user_input.lower() == 'functions':
                functions = controller.get_available_functions()
                print(f"\n⚡ Available Functions:")
                for agent_name, func_list in functions.items():
                    print(f"\n  🤖 {agent_name}:")
                    for func in func_list:
                        print(f"    • {func['name']}: {func['description']}")
                continue
            
            # Process as regular message
            print(f"\n🔄 Processing: {user_input}")
            result = await controller.process_user_message(user_input)
            
            if result.get("status") == "success":
                print("✅ Task completed successfully!")
                
                # Display conversation
                task_result = result.get("result", {})
                if "messages" in task_result:
                    print("\n💬 Conversation:")
                    for msg in task_result["messages"]:
                        role = msg.get("role", "unknown")
                        content = msg.get("content", "")
                        name = msg.get("name", role)
                        print(f"  {name}: {content[:200]}{'...' if len(content) > 200 else ''}")
                
                if "summary" in task_result:
                    print(f"\n📋 Summary: {task_result['summary']}")
            else:
                print(f"❌ Error: {result.get('message', 'Unknown error')}")
                
        except KeyboardInterrupt:
            logger.info("\nReceived interrupt signal. Shutting down...")
            break
        except Exception as e:
            logger.error(f"Error in CLI mode: {e}")
            print(f"❌ Error: {e}")

def print_help():
    """Print CLI help information"""
    help_text = """
🔧 KRATOS CLI Commands:

System Commands:
  help        - Show this help message
  status      - Show system status
  functions   - List available agent functions
  quit/exit/q - Exit KRATOS

Task Examples:
  "Show me all pods in the default namespace"
  "Restart the nginx deployment in staging" 
  "Get cluster health status"
  "Scale the web-app deployment to 5 replicas"
  "Show logs for pod my-pod-name"
  "Get node metrics and resource usage"

Agent Operations:
  All natural language requests are processed by the AutoGen system
  and routed to appropriate agents automatically.
"""
    print(help_text)

async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="KRATOS - Kubernetes Runtime Agentic Operating System")
    parser.add_argument("--mode", choices=["cli", "dashboard"], default="dashboard",
                       help="Run mode: cli for interactive terminal, dashboard for web UI")
    parser.add_argument("--config", help="Configuration file path")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    
    args = parser.parse_args()
    
    # Set debug logging
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Load configuration
    logger.info("🔧 Loading KRATOS configuration...")
    config = load_configuration()
    
    # Validate configuration
    if not config["api_key"]:
        logger.error("❌ OPENAI_API_KEY not found in environment variables")
        logger.error("Please set your OpenAI API key in the .env file or environment")
        sys.exit(1)
    
    azure_config = config["azure"]
    required_azure_vars = ["subscription_id", "resource_group", "cluster_name"]
    missing_vars = [var for var in required_azure_vars if not azure_config.get(var)]
    
    if missing_vars:
        logger.error(f"❌ Missing required Azure configuration: {', '.join(missing_vars)}")
        logger.error("Please check your .env file or environment variables")
        sys.exit(1)
    
    logger.info("✅ Configuration loaded successfully")
    
    # Initialize controller
    logger.info("🚀 Initializing KRATOS Controller...")
    controller = KratosController(config)
    
    if not await controller.initialize():
        logger.error("❌ Failed to initialize KRATOS Controller")
        sys.exit(1)
    
    logger.info("✅ KRATOS Controller initialized successfully")
    
    try:
        # Run based on mode
        if args.mode == "cli":
            await run_cli_mode(controller)
        else:
            logger.info("🌐 Starting KRATOS Dashboard...")
            logger.info("Please run: streamlit run ui/dashboard.py")
            print("\n" + "="*60)
            print("🚀 KRATOS Dashboard")
            print("="*60)
            print("To start the web interface, run:")
            print("  streamlit run ui/dashboard.py")
            print("\nOr use CLI mode:")
            print("  python main.py --mode cli")
            print("="*60)
    
    except KeyboardInterrupt:
        logger.info("Received interrupt signal...")
    except Exception as e:
        logger.error(f"Error in main: {e}")
    finally:
        # Cleanup
        await controller.shutdown()
        logger.info("🛑 KRATOS shutdown complete")

if __name__ == "__main__":
    # Handle asyncio event loop for different environments
    try:
        asyncio.run(main())
    except RuntimeError as e:
        if "asyncio.run() cannot be called from a running event loop" in str(e):
            # In Jupyter or similar environments
            loop = asyncio.get_event_loop()
            loop.run_until_complete(main())
        else:
            raise