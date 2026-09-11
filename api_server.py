import os
import logging

import dns
# FastAPI and related
from fastapi import FastAPI, Request, status, APIRouter, Security, HTTPException, Depends
from fastapi.openapi.docs import get_redoc_html
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from dotenv import load_dotenv
from starlette.responses import HTMLResponse
from contextlib import asynccontextmanager

import dns_server
import database

# Load environment variables from .env file
load_dotenv()

# Get ports from environment variables with defaults
DNS_PORT = int(os.getenv("DNS_PORT", 1053))
API_PORT = int(os.getenv("API_PORT", 8000))
STANDALONE = bool(os.getenv("STANDALONE", "true") == "true")

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')


# Load environment variables from .env file
load_dotenv()
@asynccontextmanager
async def lifespan(app):
    logging.info("FastAPI lifespan startup: initializing DB and starting DNS server thread.")
    database.init_db()
    dns_server.start_dns_server_thread()
    yield
    logging.info("FastAPI lifespan shutdown: stopping DNS server thread.")
    dns_server.stop_dns_server_thread()

app = FastAPI(
    title="OpenDNS",
    version="1.0.0",
    description="""""",
    openapi_url="/openapi.json",
    contact={
        "name": "Sanyam Malik",
        "email": "sanyammalik105@gmail.com",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan
)
# Mount static before including routers
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = os.getenv("API_KEY", None)
async def check_auth(api_key: str = Security(APIKeyHeader(name="x-api-key", auto_error=True)) if API_KEY else None):
    if API_KEY is None:
        return
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid API Key")

router = APIRouter()

# Main landing page: register directly on app!
@app.get("/", include_in_schema=False)
async def ui(request: Request):
    if STANDALONE:
        return templates.TemplateResponse("index.html", {"request": request})
    else:
        return {"message": "OpenDNS is running...."}

@router.get("/config", dependencies=[Depends(check_auth)])
async def get_config():
    config = database.get_full_config()
    return JSONResponse(config)

@router.post("/config", dependencies=[Depends(check_auth)])
async def update_config(request: Request):
    new_config = await request.json()
    resolvers = new_config.get("resolvers") or ["8.8.8.8"]
    # Reset resolvers: naive approach (remove all and add provided)
    existing = set(database.list_resolvers())
    for r in existing:
        database.remove_resolver(r)
    for r in resolvers:
        database.add_resolver(r)
    # Domains
    domains = new_config.get("domains", {})
    # Replace all domains with provided config
    current = database.get_domains_config().keys()
    for d in list(current):
        database.delete_domain(d)
    for domain, payload in domains.items():
        database.upsert_domain(domain, payload.get("ip"), payload.get("subdomains", {}))
    reload_dns()
    return JSONResponse({"message": "Config updated"}, status_code=status.HTTP_200_OK)

@router.get("/resolvers", dependencies=[Depends(check_auth)])
async def get_resolvers():
    return JSONResponse({"resolvers": database.list_resolvers()})

@router.post("/resolver", dependencies=[Depends(check_auth)])
async def add_resolver(request: Request):
    data = await request.json()
    ip = data.get("ip")
    if not ip:
        return JSONResponse({"error": "Missing ip"}, status_code=status.HTTP_400_BAD_REQUEST)
    # Ensure at least default exists if empty
    if not database.list_resolvers():
        database.add_resolver("8.8.8.8")
    database.add_resolver(ip)
    reload_dns()
    return JSONResponse({"message": f"Resolver {ip} added."}, status_code=status.HTTP_200_OK)

@router.delete("/resolver", dependencies=[Depends(check_auth)])
async def delete_resolver(request: Request):
    data = await request.json()
    ip = data.get("ip")
    if not ip:
        return JSONResponse({"error": "Missing ip"}, status_code=status.HTTP_400_BAD_REQUEST)
    if database.remove_resolver(ip):
        reload_dns()
        return JSONResponse({"message": "Resolver removed"}, status_code=status.HTTP_200_OK)
    return JSONResponse({"error": "Resolver not found"}, status_code=status.HTTP_404_NOT_FOUND)

@router.get("/domains", dependencies=[Depends(check_auth)])
async def get_domains():
    return JSONResponse({"domains": database.get_domains_config()})

@router.post("/domain", dependencies=[Depends(check_auth)])
async def add_or_update_domain(request: Request):
    data = await request.json()
    domain = data.get("domain")
    ip = data.get("ip")
    subdomains = data.get("subdomains", {})
    if not domain:
        return JSONResponse({"error": "Missing domain"}, status_code=status.HTTP_400_BAD_REQUEST)
    # Normalize CSV lists if provided as strings
    if isinstance(ip, str) and ',' in ip:
        ip = [i.strip() for i in ip.split(',')]
    for sub, sub_ip in list(subdomains.items()):
        if isinstance(sub_ip, str) and ',' in sub_ip:
            subdomains[sub] = [i.strip() for i in sub_ip.split(',')]
    database.upsert_domain(domain, ip, subdomains)
    reload_dns()
    return JSONResponse({"message": f"Domain {domain} added/updated."}, status_code=status.HTTP_200_OK)

@router.delete("/domain", dependencies=[Depends(check_auth)])
async def delete_domain(request: Request):
    data = await request.json()
    domain = data.get("domain")
    if not domain:
        return JSONResponse({"error": "Missing domain"}, status_code=status.HTTP_400_BAD_REQUEST)
    if database.delete_domain(domain):
        reload_dns()
        return JSONResponse({"message": f"Domain {domain} removed."}, status_code=status.HTTP_200_OK)
    return JSONResponse({"error": "Domain not found"}, status_code=status.HTTP_404_NOT_FOUND)

@router.get("/subdomains", dependencies=[Depends(check_auth)])
async def get_subdomains(request: Request):
    data = await request.json()
    domain = data.get("domain") if data else None
    domains = database.get_domains_config()
    if domain in domains:
        return JSONResponse(domains[domain].get("subdomains", {}))
    return JSONResponse({})

@router.post("/subdomain", dependencies=[Depends(check_auth)])
async def add_or_update_subdomain(request: Request):
    data = await request.json()
    domain = data.get("domain")
    subdomain = data.get("subdomain")
    ip = data.get("ip")
    if not domain or not subdomain or not ip:
        return JSONResponse({"error": "Missing domain/subdomain/ip"}, status_code=status.HTTP_400_BAD_REQUEST)
    if isinstance(ip, str) and ',' in ip:
        ip = [i.strip() for i in ip.split(',')]
    database.upsert_subdomain(domain, subdomain, ip)
    reload_dns()
    return JSONResponse({"message": f"Subdomain {subdomain} added/updated under domain {domain}."}, status_code=status.HTTP_200_OK)

@router.delete("/subdomain", dependencies=[Depends(check_auth)])
async def delete_subdomain(request: Request):
    data = await request.json()
    domain = data.get("domain")
    subdomain = data.get("subdomain")
    if not domain or not subdomain:
        return JSONResponse({"error": "Missing domain/subdomain"}, status_code=status.HTTP_400_BAD_REQUEST)
    if database.remove_subdomain(domain, subdomain):
        reload_dns()
        return JSONResponse({"message": f"Subdomain {subdomain} removed from domain {domain}."}, status_code=status.HTTP_200_OK)
    return JSONResponse({"error": f"Subdomain {subdomain} not found in domain {domain}."}, status_code=status.HTTP_404_NOT_FOUND)

@router.post("/dig", dependencies=[Depends(check_auth)])
async def perform_dig(request: Request):
    data = await request.json()
    domain = data.get("domain")
    if not domain:
        return JSONResponse({"error": "No domain provided"}, status_code=status.HTTP_400_BAD_REQUEST)
    try:
        query = dns.message.make_query(domain, dns.rdatatype.A)
        response = dns.query.udp(query, "127.0.0.1", port=DNS_PORT, timeout=3)
        result_lines = []
        for answer in response.answer:
            for item in answer.items:
                result_lines.append(f"{domain} A {item.address}")
        return JSONResponse({"output": "\n".join(result_lines) or "No A records found."}, status_code=status.HTTP_200_OK)
    except Exception as e:
        logging.error(f"UDP DNS query failed: {e}")
        return JSONResponse({"error": str(e)}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

@router.get("/health", include_in_schema=False)
async def root():
    return {"message": "OpenDNS is running...."}


@router.get("/documentation", include_in_schema=False, response_class=HTMLResponse)
async def redoc_docs():
    return get_redoc_html(
        openapi_url="/api/dns/openapi.json",
        title="OpenLambda API Docs",
        redoc_js_url="https://cdn.jsdelivr.net/npm/redoc@next/bundles/redoc.standalone.js"
    )

app.include_router(router, prefix="/api")


def start_api_server(host='0.0.0.0', port=API_PORT):
    logging.info(f"API server running on http://{host}:{port}")
    uvicorn.run("api_server:app", host=host, port=port, reload=True)

def reload_dns():
    import time
    for attempt in range(5):
        result = dns_server.reload_dns_server_thread()
        if result:
            database.cache_clear()
            logging.debug("DNS Server Status: Restarted (cache cleared)")
            return
        logging.warning(f"DNS reload failed on attempt {attempt+1}/5. Waiting and retrying...")
        time.sleep(1)
    logging.error("DNS server failed to reload after several retries. Is another process binding the port?")


if __name__ == "__main__":
    start_api_server()