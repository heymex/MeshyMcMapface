#!/usr/bin/env python3
"""
Run MeshyMcMapface Multi-Server Agent locally
Configured to use physically connected Meshtastic node and report to localhost
"""
import subprocess
import sys
from pathlib import Path

def main():
    """Run the multi-server agent with local configuration"""
    # Change to script directory
    script_dir = Path(__file__).parent
    config_file = script_dir / 'multi_agent_config.ini'
    
    # Check if config exists
    if not config_file.exists():
        print(f"Configuration file {config_file} not found!")
        print("Make sure multi_agent_config.ini exists in the project directory.")
        sys.exit(1)
    
    # Run the modular agent
    cmd = [
        sys.executable, 
        'mmm-agent-modular.py',
        '--config', str(config_file),
        '--agent-type', 'multi_server',
        '--log-level', 'INFO'
    ]
    
    print("Starting MeshyMcMapface Multi-Server Agent...")
    print(f"Configuration: {config_file}")
    print("Server: localhost:8082")
    print("Meshtastic: Auto-detect connected device")
    print("Route Discovery: Every 1 minute")
    print()
    print("Press Ctrl+C to stop")
    print("-" * 50)
    
    try:
        # Change to script directory and run
        subprocess.run(cmd, cwd=script_dir)
    except KeyboardInterrupt:
        print("\nAgent stopped by user")
    except Exception as e:
        print(f"Error running agent: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()