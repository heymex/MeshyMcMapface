# Docker Container Architecture Plan for MeshyMcMapface

## Overview

This plan outlines a production-ready Docker containerization strategy with separate containers for the agent and server components, designed for scalability, maintainability, and ease of deployment.

---

## 1. Container Architecture

### **1.1 Base Image Strategy**
- **Base**: `python:3.11-slim-bullseye` (smaller footprint, security updates)
- **Multi-stage builds**: Separate build and runtime stages to minimize final image size
- **Common base layer**: Shared dependencies for both agent and server

### **1.2 Container Separation**

#### **Server Container (`meshymcmapface-server`)**
- **Purpose**: Central data aggregation and web dashboard
- **Ports**: 8082 (HTTP API/Dashboard)
- **Storage**: Persistent volumes for SQLite database
- **Network**: Bridge network for agent communication

#### **Agent Container (`meshymcmapface-agent`)**
- **Purpose**: Meshtastic device monitoring and data collection
- **Device Access**: USB serial device passthrough (`/dev/ttyUSB*`, `/dev/ttyACM*`)
- **Network**: Client connection to server
- **Privilege**: `--privileged` or specific device permissions for hardware access

---

## 2. Dockerfile Design

### **2.1 Server Dockerfile (`Dockerfile.server`)**

```dockerfile
# Multi-stage build for server
FROM python:3.11-slim-bullseye AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.11-slim-bullseye AS runtime

# Security: non-root user
RUN groupadd -r meshymcmapface && useradd -r -g meshymcmapface meshymcmapface

WORKDIR /app

# Copy Python packages from builder
COPY --from=builder /root/.local /home/meshymcmapface/.local

# Copy application code
COPY --chown=meshymcmapface:meshymcmapface mmm-server.py .
COPY --chown=meshymcmapface:meshymcmapface src/ ./src/

# Create directories for configs and data
RUN mkdir -p /data /config && \
    chown -R meshymcmapface:meshymcmapface /data /config

USER meshymcmapface

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8082/api/stats')"

ENV PATH="/home/meshymcmapface/.local/bin:${PATH}"
ENV PYTHONUNBUFFERED=1

EXPOSE 8082

ENTRYPOINT ["python", "mmm-server.py"]
CMD ["--config", "/config/server_config.ini", "--log-level", "INFO"]
```

### **2.2 Agent Dockerfile (`Dockerfile.agent`)**

```dockerfile
# Multi-stage build for agent
FROM python:3.11-slim-bullseye AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.11-slim-bullseye AS runtime

# Install USB/Serial support libraries
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        usbutils \
        libusb-1.0-0 \
        && rm -rf /var/lib/apt/lists/*

# Security: non-root user (but in dialout group for device access)
RUN groupadd -r meshymcmapface && \
    useradd -r -g meshymcmapface -G dialout,plugdev meshymcmapface

WORKDIR /app

# Copy Python packages from builder
COPY --from=builder /root/.local /home/meshymcmapface/.local

# Copy application code
COPY --chown=meshymcmapface:meshymcmapface mmm-agent-modular.py .
COPY --chown=meshymcmapface:meshymcmapface meshtastic_traceroute_integration.py .
COPY --chown=meshymcmapface:meshymcmapface src/ ./src/

# Create directories for configs and data
RUN mkdir -p /data /config && \
    chown -R meshymcmapface:meshymcmapface /data /config

USER meshymcmapface

ENV PATH="/home/meshymcmapface/.local/bin:${PATH}"
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "mmm-agent-modular.py"]
CMD ["--config", "/config/multi_agent_config.ini", "--log-level", "INFO"]
```

---

## 3. Docker Compose Orchestration

### **3.1 Basic docker-compose.yml**

```yaml
version: '3.8'

services:
  server:
    build:
      context: .
      dockerfile: Dockerfile.server
    container_name: meshymcmapface-server
    restart: unless-stopped
    ports:
      - "8082:8082"
    volumes:
      - ./data/server:/data
      - ./config/server_config.ini:/config/server_config.ini:ro
    networks:
      - meshymcmapface
    environment:
      - TZ=America/Chicago
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8082/api/stats')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  agent:
    build:
      context: .
      dockerfile: Dockerfile.agent
    container_name: meshymcmapface-agent
    restart: unless-stopped
    depends_on:
      server:
        condition: service_healthy
    volumes:
      - ./data/agent:/data
      - ./config/multi_agent_config.ini:/config/multi_agent_config.ini:ro
    devices:
      - /dev/ttyUSB0:/dev/ttyUSB0  # Adjust to your device
    networks:
      - meshymcmapface
    environment:
      - TZ=America/Chicago
    # Uncomment for USB device auto-discovery
    # privileged: true

networks:
  meshymcmapface:
    driver: bridge
```

### **3.2 Multi-Agent docker-compose.yml**

```yaml
version: '3.8'

services:
  server:
    build:
      context: .
      dockerfile: Dockerfile.server
    container_name: meshymcmapface-server
    restart: unless-stopped
    ports:
      - "8082:8082"
    volumes:
      - ./data/server:/data
      - ./config/server_config.ini:/config/server_config.ini:ro
    networks:
      - meshymcmapface

  agent-001:
    build:
      context: .
      dockerfile: Dockerfile.agent
    container_name: meshymcmapface-agent-001
    restart: unless-stopped
    depends_on:
      - server
    volumes:
      - ./data/agent-001:/data
      - ./config/agent-001-config.ini:/config/multi_agent_config.ini:ro
    devices:
      - /dev/ttyUSB0:/dev/ttyUSB0
    networks:
      - meshymcmapface
    environment:
      - AGENT_ID=agent-001

  agent-002:
    build:
      context: .
      dockerfile: Dockerfile.agent
    container_name: meshymcmapface-agent-002
    restart: unless-stopped
    depends_on:
      - server
    volumes:
      - ./data/agent-002:/data
      - ./config/agent-002-config.ini:/config/multi_agent_config.ini:ro
    devices:
      - /dev/ttyUSB1:/dev/ttyUSB1
    networks:
      - meshymcmapface
    environment:
      - AGENT_ID=agent-002

networks:
  meshymcmapface:
    driver: bridge
```

---

## 4. Volume and Storage Strategy

### **4.1 Persistent Volumes**

```yaml
volumes:
  # Server data
  - ./data/server:/data                    # SQLite database
  - ./config/server_config.ini:/config/server_config.ini:ro

  # Agent data
  - ./data/agent:/data                     # Local buffer database
  - ./config/multi_agent_config.ini:/config/multi_agent_config.ini:ro
```

### **4.2 Directory Structure**

```
MeshyMcMapface/
├── docker/
│   ├── Dockerfile.server
│   ├── Dockerfile.agent
│   ├── docker-compose.yml
│   └── docker-compose.multi-agent.yml
├── config/
│   ├── server_config.ini
│   ├── multi_agent_config.ini
│   ├── agent-001-config.ini
│   └── agent-002-config.ini
├── data/
│   ├── server/
│   │   └── distributed_meshview.db
│   └── agent/
│       └── local_buffer.db
```

---

## 5. Device Access Strategies

### **5.1 USB Serial Device Access**

#### **Option 1: Direct Device Mapping (Recommended)**
```yaml
devices:
  - /dev/ttyUSB0:/dev/ttyUSB0
  - /dev/ttyACM0:/dev/ttyACM0
```

#### **Option 2: Privileged Container (Development Only)**
```yaml
privileged: true
volumes:
  - /dev:/dev
```

#### **Option 3: Device Permissions (Balanced)**
```yaml
user: "1000:20"  # dialout group
devices:
  - /dev/ttyUSB0:/dev/ttyUSB0
group_add:
  - dialout
```

### **5.2 TCP/BLE Connections**

For TCP or BLE connections, no special device access needed:

```yaml
# Agent using TCP connection
environment:
  - MESHTASTIC_CONNECTION=tcp
  - MESHTASTIC_HOST=192.168.1.100
```

---

## 6. Network Configuration

### **6.1 Internal Communication**

```yaml
networks:
  meshymcmapface:
    driver: bridge
    ipam:
      config:
        - subnet: 172.28.0.0/16
```

### **6.2 Server Discovery**

Agents reference server by service name:

```ini
[server_primary]
url = http://server:8082
```

### **6.3 External Access**

```yaml
ports:
  - "8082:8082"              # Web dashboard
  - "0.0.0.0:8082:8082"      # All interfaces
  - "127.0.0.1:8082:8082"    # Localhost only
```

---

## 7. Configuration Management

### **7.1 Environment Variables**

```yaml
environment:
  - AGENT_ID=${AGENT_ID:-agent-001}
  - SERVER_URL=${SERVER_URL:-http://server:8082}
  - LOG_LEVEL=${LOG_LEVEL:-INFO}
  - DB_PATH=/data/${AGENT_ID}.db
```

### **7.2 Config File Templates**

**Server config template** (`config/server_config.ini.template`):
```ini
[server]
host = 0.0.0.0
port = 8082

[database]
path = /data/distributed_meshview.db

[api_keys]
agent-001 = ${AGENT_001_KEY}
```

**Agent config template** (`config/multi_agent_config.ini.template`):
```ini
[agent]
id = ${AGENT_ID}
location_name = ${LOCATION_NAME}

[server_primary]
url = http://server:8082
api_key = ${API_KEY}
```

---

## 8. Security Considerations

### **8.1 Non-Root Execution**
- Both containers run as non-root user `meshymcmapface`
- Agent user added to `dialout` and `plugdev` groups for device access

### **8.2 Read-Only Configs**
```yaml
volumes:
  - ./config/server_config.ini:/config/server_config.ini:ro
```

### **8.3 Secret Management**

```yaml
secrets:
  agent_api_key:
    file: ./secrets/agent_api_key.txt

services:
  agent:
    secrets:
      - agent_api_key
    environment:
      - API_KEY_FILE=/run/secrets/agent_api_key
```

### **8.4 Network Isolation**
```yaml
networks:
  meshymcmapface:
    internal: true  # No external access except exposed ports
```

---

## 9. Deployment Scenarios

### **9.1 Single Host Deployment**
```bash
docker-compose up -d
```

### **9.2 Multi-Host Deployment**

**Server host**:
```yaml
services:
  server:
    ports:
      - "8082:8082"
    networks:
      - overlay_network
```

**Agent hosts** (remote locations):
```yaml
services:
  agent:
    environment:
      - SERVER_URL=http://server-host.example.com:8082
```

### **9.3 Docker Swarm Deployment**

```yaml
version: '3.8'
services:
  server:
    deploy:
      replicas: 1
      placement:
        constraints:
          - node.role == manager

  agent:
    deploy:
      mode: global  # One agent per node
      placement:
        constraints:
          - node.labels.meshtastic == true
```

---

## 10. Health Checks and Monitoring

### **10.1 Container Health**

```yaml
healthcheck:
  test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8082/api/stats')"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

### **10.2 Logging**

```yaml
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
```

### **10.3 Monitoring Integration**

```yaml
# Prometheus metrics export
ports:
  - "9090:9090"  # Metrics endpoint

# JSON TCP logging to external collector
environment:
  - JSON_LOG_HOST=logstash.example.com
  - JSON_LOG_PORT=5140
```

---

## 11. Build and Deployment Commands

### **11.1 Build Images**
```bash
# Build both images
docker-compose build

# Build specific service
docker-compose build server
docker-compose build agent
```

### **11.2 Run Containers**
```bash
# Start all services
docker-compose up -d

# Start specific service
docker-compose up -d server

# View logs
docker-compose logs -f agent
docker-compose logs -f server
```

### **11.3 Maintenance**
```bash
# Stop all services
docker-compose down

# Restart service
docker-compose restart agent

# Update and restart
docker-compose pull
docker-compose up -d
```

---

## 12. Best Practices Summary

1. ✅ **Use multi-stage builds** to minimize image size
2. ✅ **Run as non-root user** for security
3. ✅ **Mount configs as read-only** volumes
4. ✅ **Use health checks** for automatic recovery
5. ✅ **Implement proper logging** with rotation
6. ✅ **Use named volumes** for persistent data
7. ✅ **Leverage Docker networks** for service discovery
8. ✅ **Tag images** with version numbers for rollback
9. ✅ **Use .dockerignore** to exclude unnecessary files
10. ✅ **Document device requirements** clearly

---

## 13. Next Steps

1. Create `Dockerfile.server` and `Dockerfile.agent`
2. Create `docker-compose.yml` with basic configuration
3. Create `.dockerignore` file
4. Create configuration templates in `config/` directory
5. Add Docker documentation to `README.md`
6. Create startup scripts for initialization
7. Test with sample configurations
8. Create CI/CD pipeline for automated builds
