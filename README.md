# stormlit
A streamlit application designed for interacting with probabilistic flood hazards modeling data 

## Stormlit Development Environment
The development container provides a consistent environment for Stormlit development with Python (via Micromamba), Node.js, AWS CLI, CDKTF, Keycloak, and PostgreSQL.

### Prerequisites Installation

1. Install Docker Desktop:
   - Windows/Mac: Download from [Docker Desktop](https://www.docker.com/products/docker-desktop)
   - Linux: Follow [Docker Engine installation](https://docs.docker.com/engine/install/)

2. Install VS Code:
   - Download from [Visual Studio Code](https://code.visualstudio.com/)

3. Install VS Code Extensions:
   - Open VS Code
   - Press Ctrl+Shift+X (Windows/Linux) or Cmd+Shift+X (Mac)
   - Search and install "Dev Containers"

### Setup Steps

1. Clone the repository:
```bash
git clone https://github.com/fema-ffrd/stormlit
cd stormlit
```

2. Open in VS Code:
```bash
code .
```

3. Start Dev Container:
   - Press F1 or Ctrl+Shift+P
   - Type "Dev Containers: Open Folder in Container"
   - Select your project folder
   - Wait for container build (~5-10 minutes first time)

4. Verify services:
   - Open browser: http://localhost:50080 (Keycloak)
     - Login: admin/admin
   - Open browser: http://localhost:55050 (pgAdmin)
     - Login: admin@example.com/admin
     - Add server:
       1. Right click "Servers" → "Register" → "Server"
       2. Name: "Stormlit DB"
       3. Connection tab:
          - Host: stormlit-postgres
          - Port: 5432
          - Database: stormlit_keycloak_db
          - Username: keycloak
          - Password: keycloak

5. Start developing:
   - Code is synced between your machine and container
   - Python environment is pre-configured
   - Terminal in VS Code uses the container environment

### Base Image and Features
- Base image: `mcr.microsoft.com/devcontainers/base:jammy`
- Python environment managed by Micromamba
- Node.js LTS
- AWS CLI
- CDKTF v0.20.10

### Services

#### Keycloak (Identity and Access Management)
- Container: `stormlit-keycloak`
- URL: http://localhost:50080
- Admin credentials: admin/admin
- Backed by PostgreSQL

#### PostgreSQL
- Container: `stormlit-postgres`
- Port: 55432
- Database: stormlit_keycloak_db
- Credentials: keycloak/keycloak
- Volume: stormlit-postgres-data

#### pgAdmin (Database Management)
- Container: `stormlit-pgadmin`
- URL: http://localhost:55050
- Login: admin@example.com/admin

### Environment Configurations
- Python path: `/opt/conda/envs/stormlit/bin/python`
- Workspace mounted at: `/workspace`
- Environment file: `/workspace/env.yml`

### Included VS Code Extensions
- Python
- Pylint
- GitHub Copilot
- Black Formatter

### Post-Creation Commands
The container automatically:
- Sets workspace ownership to vscode user
- Initializes Micromamba shell
- Activates stormlit environment
- Configures Git safe directory

### Networking
All services are connected via `stormlit-network` for internal communication.

### Data Persistence
- PostgreSQL data: `stormlit-postgres-data` volume
- Project files: Mounted from host at `/workspace`


## Running Streamlit

### Local Development
```bash
# In VS Code terminal
streamlit run app.py
```
Access at http://localhost:8501

### Port Configuration
- Streamlit default port: 8501
- Configure in `.streamlit/config.toml`:
```toml
[server]
port = 8501
```

### Hot Reload
- Code changes trigger automatic reload
- Disable in config.toml:
```toml
[server]
runOnSave = false
```

### Environment Variables
1. Copy the template:
```bash
cp .env.template .env
```

2. Update `.env` with development values:

The `.env.template` file in the project root contains all required environment variables with descriptions.
