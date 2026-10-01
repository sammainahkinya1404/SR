from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import (
    accounts,
    businesses,
    credit,
    finance,
    inventory,
    pricing,
    products,
    reports,
    sales,
    sets,
    stock_in,
)
from app.services import alerts
from app.services.errors import ServiceError


def create_app() -> FastAPI:
    app = FastAPI(title="Retail Management API", version="0.1.0")

    @app.exception_handler(ServiceError)
    def _service_error(_: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    alerts.register()  # real-time low-stock checks on domain events
    modules = (
        businesses,
        inventory,
        products,
        sets,
        stock_in,
        pricing,
        sales,
        accounts,
        finance,
        credit,
        reports,
    )
    for module in modules:
        app.include_router(module.router)
    return app


app = create_app()
