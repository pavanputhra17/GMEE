#test comment
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import (
    auth,
    verdicts,
    collection,
    corpus,
    dashboard,
    evolution,
    graph,
    health,
    nlp,
    preprocessing,
)
from app.core import scheduler
from app.core.config import get_settings
from app.core.ops_security import install_rate_limiter, install_security_headers
from app.services.nlp.embedding_service import EmbeddingService
from app.services.nlp.entity_extractor import EntityExtractor
from app.services.seeder import seed_sources


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load heavy NLP models on startup
    EntityExtractor.load_model()
    EmbeddingService.load_model()
    # Startup
    await seed_sources()
    scheduler.start_scheduler()
    yield
    # Shutdown
    scheduler.stop_scheduler()

def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="GMEE API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    install_security_headers(app)
    install_rate_limiter(app)

    api_router = APIRouter()
    api_router.include_router(health.router, prefix="/health", tags=["health"])
    api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
    api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
    api_router.include_router(collection.router, prefix="/collection", tags=["Collection"])
    api_router.include_router(preprocessing.router, prefix="/preprocessing", tags=["Preprocessing"])
    api_router.include_router(nlp.router, prefix="/nlp", tags=["NLP"])
    api_router.include_router(evolution.router, prefix="/evolution", tags=["Evolution"])
    api_router.include_router(corpus.router, prefix="/corpus", tags=["Corpus"])
    api_router.include_router(verdicts.router, prefix="/verdicts", tags=["Verdicts"])
    api_router.include_router(graph.router, prefix="/graph", tags=["Graph"])

    app.include_router(api_router, prefix="/api/v1")

    return app

app = create_app()
