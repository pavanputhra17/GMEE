# GMEE (Global Misinformation Evolution Engine)

This is the development repository for GMEE.

## Setup Instructions

1. **Clone the repository.**
2. **Environment Variables**:
   Copy the example environment file and adjust if necessary (the defaults work out of the box for dev).
   ```bash
   cp .env.example .env
   ```
3. **Run Docker Compose**:
   Bring up all 5 services (postgres, neo4j, redis, backend, frontend):
   ```bash
   docker-compose -f infra/docker-compose.yml up --build
   ```
4. **Run Migrations**:
   Run Alembic migrations to set up the database schema:
   ```bash
   docker-compose -f infra/docker-compose.yml exec backend alembic upgrade head
   ```

## Development

- **Backend**: Runs at http://localhost:8000
- **Frontend**: Runs at http://localhost:3000

## Port Mappings (Host : Container)

- PostgreSQL: `55432:5432`
- Neo4j HTTP: `7474:7474`
- Neo4j Bolt: `7687:7687`
- Redis: `6379:6379`
- Backend API: `8000:8000`
- Frontend UI: `3000:3000`

## Testing

Run backend tests:
```bash
docker-compose -f infra/docker-compose.yml exec backend pytest
```

Run frontend tests:
```bash
docker-compose -f infra/docker-compose.yml exec frontend npm run test
```
