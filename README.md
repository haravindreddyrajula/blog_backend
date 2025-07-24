# FastAPI Blog Project

![Python](https://img.shields.io/badge/python-v3.11.9+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115.12-green.svg)
![SQLite](https://img.shields.io/badge/sqlite-%2307405e.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

## Table of Contents

- [Project Overview](#project-overview)
- [Features](#features)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Installation & Setup](#installation--setup)
- [Configuration](#configuration)
- [Usage](#usage)
- [API Documentation](#api-documentation)
- [Testing](#testing)
- [Deployment](#deployment)
- [Contributing](#contributing)
- [Security](#security)
- [Troubleshooting](#troubleshooting)
- [Support](#support)
- [License](#license)

## Project Overview

This is a private blog application built with modern web technologies, designed for high performance and scalability. The application provides a robust backend API for managing blog posts, user authentication, and content management.

### Tech Stack

- **Backend Framework**: FastAPI (Python)
- **Database**: SQLite (Development) / PostgreSQL (Production)
- **Authentication**: JWT-based authentication
- **Documentation**: Automatic OpenAPI/Swagger documentation
- **Testing**: PyTest
- **Code Quality**: Black, Flake8, MyPy

### Key Benefits

- âš¡ **High Performance**: Built on FastAPI for maximum speed
- ðŸ”’ **Secure**: JWT authentication and input validation
- ðŸ“š **Well Documented**: Automatic API documentation
- ðŸ§ª **Tested**: Comprehensive test suite
- ðŸ³ **Docker Ready**: Containerized for easy deployment

## Features

### Core Features
- âœ… User registration and authentication - (currently Just admin)
- âœ… CRUD operations for blog posts - Done
- âœ… Comment system - Dev done
- âœ… Category/Tag management
- âœ… Search functionality - Dev done
- âœ… User profile management

### Advanced Features
- âœ… Rate limiting
- âœ… Input validation and sanitization
- âœ… Automated database migrations
- âœ… Comprehensive logging
- âœ… Health check endpoints - just health done
- âœ… CORS configuration - Done

## Architecture

```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”    â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”    â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚   Frontend      â”‚â”€â”€â”€â”€â”‚   FastAPI       â”‚â”€â”€â”€â”€â”‚   Database      â”‚
â”‚   (Optional)    â”‚    â”‚   Backend       â”‚    â”‚   (SQLite)      â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜    â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜    â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                              â”‚
                       â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                       â”‚   External      â”‚
                       â”‚   Services      â”‚
                       â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

## Prerequisites

Before you begin, ensure you have the following installed:

- **Python 3.11+** ([Download](https://python.org/downloads/))
- **Git** ([Download](https://git-scm.com/downloads))
- **pip** (comes with Python)
- **virtualenv** (recommended for environment isolation)

### Optional Tools - In roadmap
- **Docker** (for containerized deployment)
- **PostgreSQL** (for production database)
- **Redis** (for caching and sessions)

## Installation & Setup

### 1. Clone Repository

```bash
git clone https://github.com/haravindreddyrajula/blog_backend.git
cd blog_backend
```

### 2. Environment Setup

**Create Virtual Environment:**
```bash
# Using venv (recommended)
python -m venv venv

```

**Activate Virtual Environment:**

*Windows (CMD):*
```cmd
venv\Scripts\activate
```

*Windows (PowerShell):*
```powershell
venv\Scripts\Activate.ps1
```

*macOS/Linux:*
```bash
source venv/bin/activate
```

**Verify Activation:**
You should see `(venv)` at the beginning of your command prompt.

### 3. Install Dependencies

```bash
# Install production dependencies
pip install -r requirements.txt

```

### 4. Environment Configuration

Create environment files from templates:

```bash
# Copy environment template if it exists
cp .env.example .env

# if not, create your .env file in root folder
```

Edit `.env` file with your configuration:

```env
# .env

# Use SQLite (local development)
DATABASE_URL=sqlite+aiosqlite:///./blog.db

# Or use PostgreSQL (production)
# DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/blog_db

# Database pool settings (relevant for PostgreSQL)
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=10
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=3600

# Logging SQL queries (True/False)
DB_ECHO=False


# JWT Configuration
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_MINUTES=1440
SECRET_KEY=your_production_secret_key
JWT_ALGORITHM=HS256


# DATABASE_URL = f"postgresql+asyncpg://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
```

### 5. Database Setup - in roadmap for prod

**Initialize Database:**
```bash
# Run database migrations
python -m alembic upgrade head

# Or run custom setup script
python scripts/setup_database.py
```

**Create Initial Data (Optional):**
```bash
python scripts/seed_data.py
```

### 6. Verify Installation

Run the application:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Visit these URLs to verify:
- **Application**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **ReDoc Documentation**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

## Configuration

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `APP_NAME` | Application name | FastAPI Blog | No |
| `DEBUG` | Debug mode | False | No |
| `DATABASE_URL` | Database connection string | sqlite:///./blog.db | Yes |
| `SECRET_KEY` | JWT secret key | - | Yes |
| `ALLOWED_ORIGINS` | CORS allowed origins | * | No |

### Database Configuration

**SQLite (Development):**
```env
DATABASE_URL=sqlite:///./blog.db
```

**PostgreSQL (Production):**
```env
DATABASE_URL=postgresql://username:password@localhost:5432/blog_db
```

## Usage

### Starting the Application

**Development Mode:**
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Production Mode:**
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Using Docker - in roadmap

**Build Image:**
```bash
docker build -t fastapi-blog .
```

**Run Container:**
```bash
docker run -p 8000:8000 --env-file .env fastapi-blog
```

**Using Docker Compose:**
```bash
docker-compose up -d
```

## API Documentation

### Authentication

Most endpoints require authentication. Include JWT token in headers:

```bash
Authorization: Bearer <your-jwt-token>
```

### Key Endpoints

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/health` | Health check | No |
| POST | `/auth/register` | User registration | No |
| POST | `/api/v1/auth/login` | User login | No |
| GET | `/api/v1/blogs/` | Get all posts | No |
| POST | `/api/v1/blogs/` | Create new post | Yes |
| GET | `/api/v1/blogs/{id}` | Get specific post | No |
| PUT | `/api/v1/blogs/{id}` | Update post | Yes |
| DELETE | `/api/v1/blogs/{id}` | Delete post | Yes |

### Example API Calls

**Create Post:**
```bash
curl -X POST "http://localhost:8000/api/v1/blogs/" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-token>" \
  -d '{
  "title": "string",
  "content": "string",
  "status": "DRAFT",
  "cover_image_url": "string",
  "is_public": true,
  "is_featured": false,
  "tags": "string"
}'
```

## Testing - in roadmap

### Running Tests

**Run All Tests:**
```bash
pytest
```

**Run with Coverage:**
```bash
pytest --cov=app --cov-report=html
```

**Run Specific Test File:**
```bash
pytest tests/test_auth.py
```

### Test Categories

- **Unit Tests**: Test individual functions and methods
- **Integration Tests**: Test API endpoints
- **Database Tests**: Test database operations
- **Security Tests**: Test authentication and authorization

## Deployment

### Environment Setup

1. **Production Environment Variables:**
   ```env
   DEBUG=False
   DATABASE_URL=postgresql://user:pass@host:port/db
   SECRET_KEY=production-secret-key
   ```

2. **Database Migration:**
   ```bash
   alembic upgrade head
   ```

### Deployment Options - in roadmap

**1. Traditional Server:**
```bash
# Install production server
pip install gunicorn

# Run with Gunicorn
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker
```

**2. Docker Deployment:**
```bash
docker-compose -f docker-compose.prod.yml up -d
```

**3. Cloud Platforms:**
- **Heroku**: Use provided `Procfile`
- **AWS EC2**: Use provided deployment scripts
- **Google Cloud Run**: Use Docker container
- **DigitalOcean App Platform**: Use App Spec

## Contributing

### Development Workflow

1. **Fork and Clone:**
   ```bash
   git clone https://github.com/haravindreddyrajula/blog_backend.git
   cd blog_backend
   ```

2. **Create Feature Branch:**
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Make Changes and Test:**
   ```bash
   # Make your changes
   pytest
   black .
   flake8 .
   ```

4. **Commit and Push:**
   ```bash
   git add .
   git commit -m "Add: your feature description"
   git push origin feature/your-feature-name
   ```

5. **Create Pull Request**

### Code Standards

- **Formatting**: Use Black for code formatting
- **Linting**: Use Flake8 for linting
- **Type Hints**: Use MyPy for type checking
- **Documentation**: Update docstrings and README
- **Testing**: Write tests for new features

### Commit Message Format

```
Type: Brief description

Detailed description if necessary

- Type: feat, fix, docs, style, refactor, test, chore
- Keep first line under 50 characters
- Use imperative mood
```

## Security

### Security Features

- **JWT Authentication**: Secure token-based authentication
- **Password Hashing**: Bcrypt for secure password storage
- **Input Validation**: Pydantic models for request validation
- **CORS Protection**: Configurable CORS settings
- **Rate Limiting**: Protection against abuse
- **SQL Injection Protection**: SQLAlchemy ORM prevents SQL injection

### Security Best Practices

1. **Environment Variables**: Never commit sensitive data
2. **HTTPS**: Use HTTPS in production
3. **Regular Updates**: Keep dependencies updated
4. **Access Control**: Implement proper authorization
5. **Logging**: Monitor application logs for security events

### Security Checklist

- [ ] Change default SECRET_KEY
- [ ] Use strong passwords
- [ ] Enable HTTPS
- [ ] Configure CORS properly
- [ ] Set up rate limiting
- [ ] Regular security updates
- [ ] Monitor logs

## Troubleshooting

### Common Issues

**1. ImportError: No module named 'fastapi'**
```bash
# Solution: Ensure virtual environment is activated and dependencies installed
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
```

**2. Database Connection Error**
```bash
# Solution: Check DATABASE_URL in .env file
# Ensure database exists and is accessible
```

**3. Permission Denied Error**
```bash
# Solution: Check file permissions
chmod +x scripts/setup.sh

# Or install with user flag
pip install --user -r requirements.txt
```

**4. Port Already in Use**
```bash
# Solution: Use different port
uvicorn main:app --port 8001 --reload

# Or kill process using port 8000
lsof -ti:8000 | xargs kill -9  # macOS/Linux
netstat -ano | findstr :8000   # Windows
```

**5. CORS Error**
```bash
# Solution: Add your frontend URL to ALLOWED_ORIGINS in .env
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8080
```

### Debug Mode

Enable debug mode for detailed error messages:

```env
DEBUG=True
LOG_LEVEL=DEBUG
```

### Getting Help

1. **Check Documentation**: Review this README and API docs
2. **Search Issues**: Look through existing GitHub issues
3. **Create Issue**: Submit detailed bug report with:
   - Python version
   - Operating system
   - Error messages
   - Steps to reproduce

## Support

### Resources

- **Documentation**: [API Docs](http://localhost:8000/docs)
- **Issues**: [GitHub Issues](https://github.com/haravindreddyrajula/blog_backend/issues)
- **Discussions**: [GitHub Discussions](https://github.com/haravindreddyrajula/blog_backend/discussions)

### Team Contact

- **Project Lead**: [Your Name](mailto:your.email@company.com)
- **DevOps**: [DevOps Team](mailto:devops@company.com)
- **Security**: [Security Team](mailto:security@company.com)

### Response Times

- **Critical Issues**: 4 hours
- **Bug Reports**: 24 hours
- **Feature Requests**: 1 week
- **General Questions**: 48 hours

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

### Third-Party Licenses

This project uses several third-party packages. See [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) for details.

---

## Changelog

### Version 1.0.0 (2025-01-24)
- Initial release
- User authentication system
- Blog post CRUD operations
- SQLite database integration
- API documentation
- Docker support

---

**Made with â¤ï¸ by [Weekend Dev]**

For more information, visit our [documentation](https://your-docs-site.com) or contact us at [support@yourcompany.com](mailto:support@yourcompany.com).