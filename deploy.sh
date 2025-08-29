#!/bin/bash

# Deployment Script for Elderly Care AI System

set -e

# Configuration
PROJECT_NAME="elderly-care-ai"
DOCKER_REGISTRY="ghcr.io"
GITHUB_REPO="${GITHUB_REPOSITORY:-your-org/elderly-care-ai}"
ENVIRONMENT="${1:-development}"
TAG="${2:-latest}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."

    # Check if Docker is installed
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker first."
        exit 1
    fi

    # Check if Docker Compose is installed
    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi

    # Check if Git is installed
    if ! command -v git &> /dev/null; then
        log_error "Git is not installed. Please install Git first."
        exit 1
    fi

    log_success "Prerequisites check passed"
}

# Setup environment variables
setup_environment() {
    log_info "Setting up environment for $ENVIRONMENT..."

    # Create environment-specific .env file
    cat > .env << EOF
# Environment Configuration for $ENVIRONMENT
ENVIRONMENT=$ENVIRONMENT

# Database Configuration
POSTGRES_DB=elderly_care_db
POSTGRES_USER=elderly_care
POSTGRES_PASSWORD=password123
DATABASE_URL=postgresql://elderly_care:password123@postgres:5432/elderly_care_db

# Redis Configuration
REDIS_URL=redis://redis:6379

# Application Configuration
DEBUG=false
CORS_ORIGINS=http://localhost:3000,http://frontend:3000
JWT_SECRET_KEY=your-super-secret-jwt-key-change-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24

# API Keys (Configure these for production)
OPENAI_API_KEY=${OPENAI_API_KEY:-}
TWILIO_ACCOUNT_SID=${TWILIO_ACCOUNT_SID:-}
TWILIO_AUTH_TOKEN=${TWILIO_AUTH_TOKEN:-}
TWILIO_PHONE_NUMBER=${TWILIO_PHONE_NUMBER:-}
SENDGRID_API_KEY=${SENDGRID_API_KEY:-}
TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN:-}

# Agent Configuration
HEALTH_AGENT_ENABLED=true
SAFETY_AGENT_ENABLED=true
REMINDER_AGENT_ENABLED=true

# ML Configuration
PREDICTION_ENABLED=true
ML_MODEL_PATH=./models

# File Upload Configuration
MAX_UPLOAD_SIZE=10485760
ALLOWED_EXTENSIONS=.csv,.json,.txt

# Security Configuration
BCRYPT_ROUNDS=12
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW_SECONDS=60

# Logging Configuration
LOG_LEVEL=INFO
EOF

    log_success "Environment setup completed"
}

# Build Docker images
build_images() {
    log_info "Building Docker images..."

    # Build backend image
    log_info "Building backend image..."
    docker build -t $DOCKER_REGISTRY/$GITHUB_REPO/backend:$TAG ./backend

    # Build frontend image
    log_info "Building frontend image..."
    docker build -t $DOCKER_REGISTRY/$GITHUB_REPO/frontend:$TAG ./frontend

    log_success "Docker images built successfully"
}

# Push images to registry
push_images() {
    log_info "Pushing images to registry..."

    # Login to registry (if needed)
    if [ -n "$DOCKER_REGISTRY_USERNAME" ] && [ -n "$DOCKER_REGISTRY_PASSWORD" ]; then
        echo "$DOCKER_REGISTRY_PASSWORD" | docker login $DOCKER_REGISTRY -u "$DOCKER_REGISTRY_USERNAME" --password-stdin
    fi

    # Push backend image
    log_info "Pushing backend image..."
    docker push $DOCKER_REGISTRY/$GITHUB_REPO/backend:$TAG

    # Push frontend image
    log_info "Pushing frontend image..."
    docker push $DOCKER_REGISTRY/$GITHUB_REPO/frontend:$TAG

    log_success "Images pushed to registry"
}

# Deploy with Docker Compose
deploy_compose() {
    log_info "Deploying with Docker Compose..."

    # Create necessary directories
    mkdir -p data logs monitoring/grafana/provisioning monitoring/prometheus nginx/ssl

    # Start services
    if [ "$ENVIRONMENT" = "production" ]; then
        docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
    else
        docker-compose up -d
    fi

    # Wait for services to be healthy
    log_info "Waiting for services to be healthy..."
    sleep 30

    # Check service health
    check_services_health

    log_success "Deployment completed successfully"
}

# Check service health
check_services_health() {
    log_info "Checking service health..."

    services=("postgres" "redis" "backend" "frontend")

    for service in "${services[@]}"; do
        if docker-compose ps $service | grep -q "Up"; then
            log_success "$service is running"
        else
            log_error "$service is not running"
            docker-compose logs $service
            exit 1
        fi
    done

    # Check backend health endpoint
    if curl -f http://localhost:8000/health > /dev/null 2>&1; then
        log_success "Backend health check passed"
    else
        log_error "Backend health check failed"
        exit 1
    fi
}

# Run data ingestion
run_data_ingestion() {
    log_info "Running data ingestion..."

    # Copy CSV files to data directory
    mkdir -p data
    cp *.csv data/ 2>/dev/null || true

    # Run data ingestion script
    docker-compose exec -T backend python data_ingestion.py

    log_success "Data ingestion completed"
}

# Run tests
run_tests() {
    log_info "Running tests..."

    # Run backend tests
    log_info "Running backend tests..."
    docker-compose exec -T backend python -m pytest tests/ -v

    # Run frontend tests
    log_info "Running frontend tests..."
    docker-compose exec -T frontend npm test -- --watchAll=false

    log_success "All tests passed"
}

# Initialize monitoring
setup_monitoring() {
    log_info "Setting up monitoring..."

    # Wait for Grafana to be ready
    sleep 10

    # Add data source and dashboards
    curl -X POST -H "Content-Type: application/json" \
         -d '{"name":"Prometheus","type":"prometheus","url":"http://prometheus:9090","access":"proxy"}' \
         http://admin:admin123@localhost:3001/api/datasources

    log_success "Monitoring setup completed"
}

# Main deployment function
main() {
    log_info "Starting deployment of Elderly Care AI System"
    log_info "Environment: $ENVIRONMENT"
    log_info "Tag: $TAG"

    check_prerequisites
    setup_environment

    if [ "$ENVIRONMENT" = "production" ]; then
        build_images
        push_images
    fi

    deploy_compose
    run_data_ingestion
    setup_monitoring

    log_success "🎉 Deployment completed successfully!"
    log_info ""
    log_info "Services available at:"
    log_info "  - Frontend: http://localhost:3000"
    log_info "  - Backend API: http://localhost:8000"
    log_info "  - API Documentation: http://localhost:8000/docs"
    log_info "  - Grafana: http://localhost:3001 (admin/admin123)"
    log_info "  - Prometheus: http://localhost:9090"
    log_info ""
    log_info "To view logs: docker-compose logs -f"
    log_info "To stop services: docker-compose down"
}

# Cleanup function
cleanup() {
    log_info "Cleaning up..."
    docker-compose down -v 2>/dev/null || true
    rm -f .env
}

# Handle script arguments
case "${1:-help}" in
    "development"|"dev")
        ENVIRONMENT="development"
        main
        ;;
    "staging")
        ENVIRONMENT="staging"
        main
        ;;
    "production"|"prod")
        ENVIRONMENT="production"
        main
        ;;
    "cleanup")
        cleanup
        ;;
    "test")
        run_tests
        ;;
    "build")
        build_images
        ;;
    "push")
        push_images
        ;;
    "help"|*)
        echo "Usage: $0 [environment] [tag]"
        echo ""
        echo "Environments:"
        echo "  development  - Local development environment"
        echo "  staging      - Staging environment"
        echo "  production   - Production environment"
        echo "  test         - Run tests only"
        echo "  build        - Build images only"
        echo "  push         - Push images only"
        echo "  cleanup      - Clean up containers and volumes"
        echo ""
        echo "Examples:"
        echo "  $0 development     # Deploy to development"
        echo "  $0 production v1.0 # Deploy production with tag v1.0"
        echo "  $0 test            # Run tests"
        ;;
esac
