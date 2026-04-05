from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.middleware.csrf import CSRFMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.theme import ThemeMiddleware

from .error_handlers import register_error_handlers
from .routes import auth, data, exercise, home, profile, progress, workout
from .settings import settings

app = FastAPI(title="ElbieFit")

app.mount("/static", StaticFiles(directory="static"), name="static")

register_error_handlers(app)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(ThemeMiddleware)
app.add_middleware(CSRFMiddleware, excluded_prefixes=settings.CSRF_EXCLUDED_PREFIXES)

app.include_router(home.router)
app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(workout.router)
app.include_router(exercise.router)
app.include_router(progress.router)
app.include_router(data.router)
