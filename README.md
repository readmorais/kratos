# KRATOS - Kubernetes Runtime Agentic Operating System

⚡ **KRATOS** is a sophisticated multi-agent orchestration framework designed to manage Kubernetes-native infrastructure tasks through natural language interactions. Powered by Microsoft AutoGen and featuring an intuitive Streamlit interface, KRATOS enables seamless DevOps automation with intelligent agent coordination.

## 🌟 Key Features

### Multi-Agent Architecture
- **Modular Agent System**: Extensible framework supporting multiple specialized agents
- **AutoGen Integration**: Leverages Microsoft AutoGen for intelligent conversation management
- **MCP Protocol**: Uses Model Context Protocol for secure, standardized agent communication

### k8s-agent Capabilities
- 🔍 **Cluster Monitoring**: Real-time cluster health and metrics
- 🚀 **Deployment Management**: Start, stop, restart, and scale deployments
- 📊 **Pod Operations**: List, inspect, and manage pods across namespaces
- 📜 **Manifest Management**: Apply and validate Kubernetes YAML configurations
- 📋 **Log Analysis**: Retrieve and analyze container logs
- 🔧 **Node Management**: Monitor node health and resource usage

### Intelligent Interface
- 🌐 **Streamlit Dashboard**: Modern, responsive web interface
- 💬 **Natural Language Processing**: Execute tasks using conversational commands
- 📚 **Conversation History**: Track all interactions and results
- 📊 **Real-time Monitoring**: Live cluster status and health metrics

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    KRATOS Dashboard (Streamlit)            │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐  │
│  │   Task Panel    │  │   Monitoring    │  │   History   │  │
│  └─────────────────┘  └─────────────────┘  └─────────────┘  │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                KRATOS Controller (AutoGen)                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐  │
│  │   User Proxy    │  │  Group Chat     │  │   Manager   │  │
│  └─────────────────┘  └─────────────────┘  └─────────────┘  │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                    Agent Layer                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐  │
│  │   k8s-agent     │  │  monitoring-    │  │   future    │  │
│  │                 │  │     agent       │  │   agents    │  │
│  └─────────────────┘  └─────────────────┘  └─────────────┘  │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                 MCP Integration Layer                      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐  │
│  │  AKS MCP        │  │   Other MCP     │  │   Custom    │  │
│  │  Server         │  │   Servers       │  │   Adapters  │  │
│  └─────────────────┘  └─────────────────┘  └─────────────┘  │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│              Azure Kubernetes Service                      │
│                    (Target Cluster)                        │
└─────────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- Azure CLI configured with appropriate permissions
- Access to an Azure Kubernetes Service (AKS) cluster
- OpenAI API key for AutoGen functionality

### Installation

1. **Clone the repository:**
```bash
git clone <repository-url>
cd kratos
```

2. **Install dependencies:**
```bash
pip install -r requirements.txt
```

3. **Configure environment:**
```bash
cp .env.example .env
# Edit .env with your configuration
```

4. **Set up Azure authentication:**
```bash
az login
az account set --subscription "your-subscription-id"
az aks get-credentials --resource-group "your-rg" --name "your-cluster"
```

### Configuration

Edit `.env` file with your settings:

```env
# Azure Configuration
AZURE_SUBSCRIPTION_ID=your_subscription_id
AZURE_RESOURCE_GROUP=your_resource_group
AZURE_AKS_CLUSTER_NAME=your_cluster_name

# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key

# MCP Configuration
AKS_MCP_ENDPOINT=http://localhost:3000

# Optional: Custom settings
AUTOGEN_TEMPERATURE=0.1
AUTOGEN_MAX_ROUND=10
```

## 🎮 Usage

### Dashboard Mode (Recommended)

Start the Streamlit dashboard:

```bash
streamlit run ui/dashboard.py
```

Access the interface at `http://localhost:8501`

#### Dashboard Features:
- **Task Panel**: Execute natural language commands
- **Agent Selection**: Choose specific agents or auto-route
- **Real-time Results**: See live conversation and results
- **Health Monitoring**: Check cluster status and metrics
- **History Tracking**: Review past interactions

### CLI Mode

For terminal-based interaction:

```bash
python main.py --mode cli
```

#### CLI Commands:
```bash
KRATOS> Show me all pods in the default namespace
KRATOS> Restart the nginx deployment in production
KRATOS> Get cluster health status
KRATOS> Scale the web-app to 5 replicas
KRATOS> help        # Show available commands
KRATOS> status      # System status
KRATOS> quit        # Exit
```

## 🤖 Agent Functions

### k8s-agent Functions

| Function | Description | Example Usage |
|----------|-------------|---------------|
| `get_pods` | List pods in a namespace | "Show pods in staging" |
| `restart_deployment` | Restart a deployment | "Restart nginx deployment" |
| `apply_yaml` | Apply Kubernetes manifests | "Apply this YAML config" |
| `get_node_metrics` | Get node resource info | "Show node metrics" |
| `get_cluster_health` | Overall cluster health | "Check cluster health" |
| `scale_deployment` | Scale deployment replicas | "Scale web-app to 3 replicas" |
| `get_logs` | Retrieve pod logs | "Show logs for my-pod" |

### Natural Language Examples

```bash
# Pod Management
"Show me all running pods in the kube-system namespace"
"List pods that are not running in production"

# Deployment Operations
"Restart the api-gateway deployment in staging"
"Scale the worker deployment to 10 replicas"
"Show status of all deployments"

# Monitoring & Health
"What's the health status of my cluster?"
"Show me node resource usage"
"Get recent logs from the failed pod"

# YAML Operations
"Apply this deployment configuration: [YAML content]"
"Validate this service manifest"
```

## 🔧 Advanced Configuration

### Custom Agents

Add new agents by extending the base agent class:

```python
# agents/my_custom_agent.py
from agents.base_agent import BaseAgent

class MyCustomAgent(BaseAgent):
    def __init__(self, config):
        super().__init__("my-custom-agent", config)
    
    async def my_function(self, param: str) -> dict:
        # Your custom logic
        return {"status": "success", "result": "..."}
```

Register in `configs/agents.yaml`:

```yaml
agents:
  my-custom-agent:
    name: "My Custom Agent"
    type: "custom"
    enabled: true
    functions:
      - my_function
```

### MCP Server Integration

Configure additional MCP servers:

```yaml
# configs/agents.yaml
mcp_servers:
  my-mcp-server:
    endpoint: "http://localhost:4000"
    type: "custom"
    authentication_required: true
```

### Security Configuration

- **API Keys**: Store in environment variables
- **RBAC**: Configure appropriate Kubernetes permissions
- **Network**: Secure MCP server endpoints
- **Logging**: Enable audit logging for compliance

## 🛠️ Development

### Project Structure

```
kratos/
├── agents/                 # Agent implementations
│   └── k8s_agent.py       # Kubernetes agent
├── orchestrator/           # AutoGen controller
│   └── controller.py      # Main orchestration logic
├── ui/                     # User interfaces
│   └── dashboard.py       # Streamlit dashboard
├── scripts/                # Utility scripts
│   └── aks_mcp_wrapper.py # AKS MCP integration
├── configs/                # Configuration files
│   └── agents.yaml        # Agent registry
├── main.py                 # Entry point
└── requirements.txt        # Dependencies
```

### Adding New Features

1. **New Agent**: Create in `agents/` directory
2. **New Functions**: Add to agent class and config
3. **UI Updates**: Modify dashboard components
4. **MCP Integration**: Extend wrapper classes

### Testing

```bash
# Run tests
python -m pytest tests/

# Lint code
flake8 kratos/
black kratos/

# Type checking
mypy kratos/
```

## 🔍 Troubleshooting

### Common Issues

1. **Authentication Errors**
   ```bash
   az login
   az aks get-credentials --resource-group RG --name CLUSTER
   ```

2. **Missing Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **AutoGen Configuration**
   - Verify `OPENAI_API_KEY` is set
   - Check model availability and quotas

4. **MCP Connection Issues**
   - Ensure MCP server is running
   - Verify endpoint connectivity
   - Check firewall/network settings

### Debug Mode

Enable detailed logging:

```bash
python main.py --debug --mode cli
```

Or set environment:

```env
LOG_LEVEL=DEBUG
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes
4. Add tests and documentation
5. Submit a pull request

### Development Guidelines

- Follow PEP 8 style guide
- Add type hints to all functions
- Include docstrings for public methods
- Write comprehensive tests
- Update documentation

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- **Microsoft AutoGen**: For the excellent multi-agent framework
- **Streamlit**: For the intuitive web interface framework
- **Azure Team**: For comprehensive Kubernetes services
- **MCP Protocol**: For standardized agent communication

## 📞 Support

- **Documentation**: Check this README and inline code comments
- **Issues**: Use GitHub issues for bug reports
- **Discussions**: GitHub discussions for questions
- **Community**: Join our community channels

---

🚀 **Ready to revolutionize your Kubernetes operations with KRATOS!** 

Start by setting up your environment, launching the dashboard, and asking your first question: *"What's the health of my cluster?"*