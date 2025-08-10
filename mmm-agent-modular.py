#!/usr/bin/env python3
"""
Modular MeshyMcMapface Agent
Uses the new modular architecture for better maintainability and extensibility
"""
import asyncio
import argparse
import sys
from pathlib import Path

# Add src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from src.agents.base_agent import AgentFactory
from src.core.config import create_sample_multi_config
from src.utils.logging import setup_logging


def main():
    parser = argparse.ArgumentParser(description='Modular MeshyMcMapface Agent')
    parser.add_argument('--config', default='multi_agent_config.ini',
                       help='Configuration file path')
    parser.add_argument('--create-config', action='store_true',
                       help='Create sample multi-server configuration file')
    parser.add_argument('--agent-type', default='multi_server',
                       choices=AgentFactory.get_available_agent_types(),
                       help='Type of agent to run')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                       help='Logging level')
    parser.add_argument('--log-file', 
                       help='Log file path (optional)')
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(level=args.log_level, log_file=args.log_file)
    
    if args.create_config:
        create_sample_multi_config(args.config)
        return
    
    if not Path(args.config).exists():
        print(f"Configuration file {args.config} not found.")
        print("Use --create-config to generate a sample configuration.")
        return
    
    try:
        # Create agent
        agent = AgentFactory.create_agent(args.agent_type, args.config)
        
        # Run agent
        asyncio.run(agent.run_with_cleanup())
        
    except KeyboardInterrupt:
        print("Agent stopped by user")
    except Exception as e:
        print(f"Agent error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()