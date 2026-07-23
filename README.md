# Enterprise Linux Access Self-Service Portal

Production-grade web application for managing Linux user access, sudo privileges, and provisioning across enterprise servers.

## Features

- **Azure AD SSO Authentication** - Microsoft Entra ID integration with automatic profile sync
- **Access Request Management** - Linux user creation, sudo access, renewal
- **Configurable Approval Workflow** - Sequential/parallel approvals with delegation and escalation
- **Automated SSH Provisioning** - RSA, ECDSA, ED25519 key support with concurrent execution
- **Automatic Sudo Expiry** - 90-day validity with background revocation
- **Email Notifications** - Full lifecycle notifications via SMTP
- **Role-Based Access Control** - Requester, Manager, Cloud Team, InfoSec, Admin roles
- **Admin Dashboard** - Statistics, user management, configuration, audit logs
- **Reporting** - CSV, Excel, and PDF export
- **Dark/Light Mode** - Modern responsive UI
- **Audit Logging** - Immutable audit trail for all actions

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Frontend | React 18 + Tailwind CSS + Vite |
| Backend | Python FastAPI (async) |
| Database | SQLite (swappable to PostgreSQL) |
| ORM | SQLAlchemy 2.0 (async) |
| Auth | Azure AD / MSAL |
| SSH | Paramiko / AsyncSSH |
| Email | aiosmtplib + Jinja2 |
| Scheduler | APScheduler |
| OS | Amazon Linux 2023 |

## Architecture

```
linux-access-portal/
├── backend/
│   ├── app/
│   │   ├── api/              # FastAPI routes
│   │   │   ├── routes/       # Auth, Requests, Approvals, Admin, Reports
│   │   │   └── dependencies/ # Auth dependencies
│   │   ├── core/             # Config, database, security
│   │   ├── models/           # SQLAlchemy models
│   │   ├── schemas/          # Pydantic schemas
│   │   └── services/         # Business logic
│   │       ├── auth/         # Azure AD service
│   │       ├── approval/     # Approval engine
│   │       ├── provisioning/ # SSH engine + provisioner
│   │       ├── notification/ # Email service
│   │       └── scheduler/    # Background jobs
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── components/       # React components
│   │   ├── pages/            # Page components
│   │   ├── hooks/            # Auth & theme hooks
│   │   └── services/         # API client
│   └── package.json
├── deployment/
│   ├── install.sh            # Installation script
│   ├── linux-access-portal.service  # systemd
│   └── nginx.conf            # Reverse proxy
└── docs/
```

## Quick Start

### Prerequisites
- Amazon Linux 2023 (or RHEL 8+/9+)
- Python 3.11+
- Node.js 18+
- Nginx

### Installation

```bash
# Clone or upload the application
cd /opt
git clone <repo-url> linux-access-portal
cd linux-access-portal

# Run installer (as root)
sudo bash deployment/install.sh

# Edit configuration
sudo vi /opt/linux-access-portal/backend/.env

# Start services
sudo systemctl start linux-access-portal
sudo systemctl start nginx
```

### Development

```bash
# Backend
cd backend
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

## Configuration

All settings are configurable via:
1. **Environment variables** (.env file)
2. **Admin UI** (Settings page in the portal)

### Azure AD Setup

1. Register an application in Azure Portal
2. Configure redirect URI: `https://your-domain.com/api/auth/callback`
3. Grant `User.Read` and `User.ReadBasic.All` permissions
4. Set Tenant ID, Client ID, Client Secret in .env

### SMTP Setup

Configure your email server details in .env for notifications.

### SSH Key Setup

1. Login as admin
2. Navigate to Admin > Configuration > SSH Keys
3. Upload your private key (RSA, ECDSA, or ED25519)
4. The key is encrypted at rest

## API Documentation

Once running, access:
- **Swagger UI**: `https://your-domain.com/api/docs`
- **ReDoc**: `https://your-domain.com/api/redoc`

## Access Types

| Type | Description | Validity |
|------|-------------|----------|
| User Access | Creates Linux user account | Permanent |
| Sudo Access | Grants sudo privileges | 90 days |
| Both | User + Sudo | 90 days (sudo) |
| Renew Sudo | Extends existing sudo | +90 days |

## Approval Workflow

Default chain (configurable):
1. Reporting Manager
2. Cloud Team Manager
3. Information Security

## Security

- CSRF/XSS/SQLi protection
- Encrypted secrets at rest (Fernet)
- HttpOnly secure cookies
- Rate limiting
- Input validation (Pydantic)
- Session timeout
- Immutable audit logs
- Principle of least privilege (systemd)

## License

Enterprise Internal Use Only
