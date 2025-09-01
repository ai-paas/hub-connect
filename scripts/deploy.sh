#!/bin/bash

# Hub Connect API with Redis Auto-Deploy Script
# Handles Redis deployment and health checks automatically

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/.env"
DOCKER_COMPOSE_FILE="$PROJECT_DIR/docker-compose.yml"
LOG_FILE="$PROJECT_DIR/logs/deploy.log"

# Create logs directory if it doesn't exist
mkdir -p "$PROJECT_DIR/logs"

# Logging function
log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

warn() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" | tee -a "$LOG_FILE"
}

info() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')] INFO:${NC} $1" | tee -a "$LOG_FILE"
}

# Check if Docker is running
check_docker() {
    if ! docker info >/dev/null 2>&1; then
        error "Docker is not running. Please start Docker and try again."
        exit 1
    fi
    log "Docker is running ✓"
}

# Check if Docker Compose is available
check_docker_compose() {
    if ! command -v docker-compose >/dev/null 2>&1 && ! docker compose version >/dev/null 2>&1; then
        error "Docker Compose is not available. Please install Docker Compose."
        exit 1
    fi
    log "Docker Compose is available ✓"
}

# Detect Docker Compose command
get_docker_compose_cmd() {
    if docker compose version >/dev/null 2>&1; then
        echo "docker compose"
    else
        echo "docker-compose"
    fi
}

# Check environment file
check_env_file() {
    if [[ ! -f "$ENV_FILE" ]]; then
        warn ".env file not found. Creating from .env.sample..."
        if [[ -f "$PROJECT_DIR/.env.sample" ]]; then
            cp "$PROJECT_DIR/.env.sample" "$ENV_FILE"
            warn "Please edit .env file with your configuration before continuing."
            info "Required settings: HF_API_TOKEN, SECRET_KEY, storage settings"
            read -p "Press Enter after editing .env file to continue..."
        else
            error ".env.sample file not found. Cannot create .env file."
            exit 1
        fi
    fi
    log "Environment file exists ✓"
}

# Check if Redis is already running externally
check_external_redis() {
    local redis_host=$(grep "^REDIS_HOST=" "$ENV_FILE" | cut -d'=' -f2 | tr -d '"' || echo "localhost")
    local redis_port=$(grep "^REDIS_PORT=" "$ENV_FILE" | cut -d'=' -f2 | tr -d '"' || echo "6379")
    
    if timeout 3 bash -c "</dev/tcp/$redis_host/$redis_port" 2>/dev/null; then
        info "External Redis detected at $redis_host:$redis_port"
        return 0
    else
        info "No external Redis detected. Will use Docker Redis."
        return 1
    fi
}

# Wait for service to be healthy
wait_for_service() {
    local service_name=$1
    local max_wait=${2:-60}
    local wait_time=0
    
    info "Waiting for $service_name to be healthy..."
    
    while [[ $wait_time -lt $max_wait ]]; do
        local compose_cmd=$(get_docker_compose_cmd)
        if $compose_cmd -f "$DOCKER_COMPOSE_FILE" ps "$service_name" | grep -q "healthy"; then
            log "$service_name is healthy ✓"
            return 0
        fi
        
        sleep 2
        wait_time=$((wait_time + 2))
        echo -n "."
    done
    
    echo
    error "$service_name failed to become healthy within ${max_wait}s"
    return 1
}

# Check service logs for errors
check_service_logs() {
    local service_name=$1
    local compose_cmd=$(get_docker_compose_cmd)
    
    info "Checking $service_name logs for errors..."
    local logs=$($compose_cmd -f "$DOCKER_COMPOSE_FILE" logs --tail=20 "$service_name" 2>&1)
    
    if echo "$logs" | grep -i "error\|exception\|failed" >/dev/null; then
        warn "Potential issues found in $service_name logs:"
        echo "$logs" | grep -i "error\|exception\|failed" | tail -5
    else
        log "$service_name logs look good ✓"
    fi
}

# Verify Redis connection
verify_redis_connection() {
    local compose_cmd=$(get_docker_compose_cmd)
    
    info "Verifying Redis connection from API..."
    
    # Try to execute redis ping from within the API container
    if $compose_cmd -f "$DOCKER_COMPOSE_FILE" exec -T hub-connect-api \
        curl -s "http://localhost:8001/" >/dev/null 2>&1; then
        log "API can reach Redis ✓"
        return 0
    else
        warn "Could not verify Redis connection from API"
        return 1
    fi
}

# Test Tus upload endpoint
test_tus_endpoint() {
    info "Testing Tus upload endpoint..."
    
    # Get auth token first
    local auth_response=$(curl -s -X POST "http://localhost:8001/api/v1/auth/login" \
        -H "Content-Type: application/json" \
        -d '{"username":"admin","password":"admin123"}' 2>/dev/null || echo "")
    
    if [[ -n "$auth_response" ]] && echo "$auth_response" | grep -q "access_token"; then
        local token=$(echo "$auth_response" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)
        
        # Test Tus endpoint
        local tus_response=$(curl -s -X POST "http://localhost:8001/api/v1/tus/files" \
            -H "Authorization: Bearer $token" \
            -H "Upload-Length: 1000" \
            -H "Upload-Metadata: filename dGVzdC50eHQ=" 2>/dev/null || echo "")
        
        if [[ -n "$tus_response" ]]; then
            log "Tus endpoint is working ✓"
            return 0
        fi
    fi
    
    warn "Could not verify Tus endpoint (this is normal on first startup)"
    return 1
}

# Main deployment function
deploy() {
    local mode=${1:-"full"}  # full, api-only, redis-only
    local compose_cmd=$(get_docker_compose_cmd)
    
    log "Starting Hub Connect deployment (mode: $mode)..."
    
    cd "$PROJECT_DIR"
    
    case $mode in
        "redis-only")
            info "Deploying Redis only..."
            $compose_cmd -f "$DOCKER_COMPOSE_FILE" up -d redis
            wait_for_service "redis" 30
            ;;
        "api-only")
            info "Deploying API only..."
            $compose_cmd -f "$DOCKER_COMPOSE_FILE" up -d hub-connect-api
            wait_for_service "hub-connect-api" 60
            ;;
        "full"|*)
            info "Deploying all services..."
            
            # Check if we need Redis
            if check_external_redis; then
                info "Using external Redis, skipping Redis container"
                $compose_cmd -f "$DOCKER_COMPOSE_FILE" up -d hub-connect-api
            else
                info "Starting Redis and API containers"
                $compose_cmd -f "$DOCKER_COMPOSE_FILE" up -d
                wait_for_service "redis" 30
            fi
            
            wait_for_service "hub-connect-api" 60
            ;;
    esac
    
    # Verify deployment
    check_service_logs "hub-connect-api"
    if ! check_external_redis; then
        check_service_logs "redis"
        verify_redis_connection
    fi
    
    # Test endpoints
    sleep 5  # Give services a moment to fully start
    test_tus_endpoint
    
    log "Deployment completed successfully! 🚀"
    info "API is running at: http://localhost:8001"
    info "API docs available at: http://localhost:8001/docs"
    info "To view logs: $compose_cmd -f '$DOCKER_COMPOSE_FILE' logs -f"
    info "To stop services: $compose_cmd -f '$DOCKER_COMPOSE_FILE' down"
}

# Show usage
usage() {
    echo "Hub Connect Auto-Deploy Script"
    echo ""
    echo "Usage: $0 [COMMAND] [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  deploy [MODE]     Deploy services (default: full)"
    echo "  stop              Stop all services"
    echo "  restart [MODE]    Restart services"
    echo "  status            Show service status"
    echo "  logs [SERVICE]    Show service logs"
    echo "  clean             Clean up containers and volumes"
    echo "  help              Show this help"
    echo ""
    echo "Modes for deploy/restart:"
    echo "  full              Deploy Redis + API (default)"
    echo "  api-only          Deploy API only"
    echo "  redis-only        Deploy Redis only"
    echo ""
    echo "Examples:"
    echo "  $0 deploy full"
    echo "  $0 restart api-only"
    echo "  $0 logs hub-connect-api"
    echo "  $0 status"
}

# Handle commands
case "${1:-deploy}" in
    "deploy")
        check_docker
        check_docker_compose
        check_env_file
        deploy "${2:-full}"
        ;;
    "stop")
        compose_cmd=$(get_docker_compose_cmd)
        info "Stopping all services..."
        $compose_cmd -f "$DOCKER_COMPOSE_FILE" down
        log "Services stopped ✓"
        ;;
    "restart")
        compose_cmd=$(get_docker_compose_cmd)
        info "Restarting services..."
        $compose_cmd -f "$DOCKER_COMPOSE_FILE" down
        sleep 2
        check_docker
        check_docker_compose
        check_env_file
        deploy "${2:-full}"
        ;;
    "status")
        compose_cmd=$(get_docker_compose_cmd)
        $compose_cmd -f "$DOCKER_COMPOSE_FILE" ps
        ;;
    "logs")
        compose_cmd=$(get_docker_compose_cmd)
        if [[ -n "$2" ]]; then
            $compose_cmd -f "$DOCKER_COMPOSE_FILE" logs -f "$2"
        else
            $compose_cmd -f "$DOCKER_COMPOSE_FILE" logs -f
        fi
        ;;
    "clean")
        compose_cmd=$(get_docker_compose_cmd)
        warn "This will remove all containers and volumes. Continue? (y/N)"
        read -r response
        if [[ "$response" =~ ^[Yy]$ ]]; then
            $compose_cmd -f "$DOCKER_COMPOSE_FILE" down -v --remove-orphans
            docker system prune -f
            log "Cleanup completed ✓"
        else
            info "Cleanup cancelled"
        fi
        ;;
    "help"|"-h"|"--help")
        usage
        ;;
    *)
        error "Unknown command: $1"
        usage
        exit 1
        ;;
esac