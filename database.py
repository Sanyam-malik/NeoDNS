import os
import uuid
from contextlib import contextmanager
from typing import Dict, List, Optional, Union
import logging

from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, Session
from sqlalchemy import func


DB_URL = os.getenv("DATABASE_URL", "sqlite:///dns_resolutions.db")

# Cache TTL in minutes (env), enforce minimum of 2 minutes
try:
    _ttl_min = int(os.getenv("CACHE_TTL_MINUTES", "2"))
except ValueError:
    _ttl_min = 2
CACHE_TTL_SECONDS_DEFAULT = max(_ttl_min * 60, 120)

# Enable SQLite multithread access for DNS thread usage
if DB_URL.startswith("sqlite"):
    engine = create_engine(DB_URL, future=True, echo=False, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DB_URL, future=True, echo=False)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def _uuid_str() -> str:
    return str(uuid.uuid4())


class Resolver(Base):
    __tablename__ = "resolvers"
    id = Column(String, primary_key=True, default=_uuid_str)
    ip = Column(String, unique=True, index=True, nullable=False)


class Domain(Base):
    __tablename__ = "domains"
    id = Column(String, primary_key=True, default=_uuid_str)
    name = Column(String, unique=True, index=True, nullable=False)
    ip = Column(String, nullable=True)  # comma-separated for multiple
    subdomains = relationship("Subdomain", cascade="all, delete-orphan", back_populates="domain")


class Subdomain(Base):
    __tablename__ = "subdomains"
    id = Column(String, primary_key=True, default=_uuid_str)
    domain_id = Column(String, ForeignKey("domains.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)  # sub label only, not FQDN
    ip = Column(String, nullable=False)    # comma-separated for multiple
    domain = relationship("Domain", back_populates="subdomains")
    __table_args__ = (UniqueConstraint('domain_id', 'name', name='uq_domain_sub'),)


class CacheEntry(Base):
    __tablename__ = "dns_cache"
    id = Column(String, primary_key=True, default=_uuid_str)
    domain = Column(String, nullable=False)
    subdomain = Column(String, nullable=True)
    record_type = Column(String, nullable=False)
    ip = Column(String, nullable=False)
    timestamp = Column(Integer, nullable=False)  # epoch seconds
    __table_args__ = (UniqueConstraint('domain', 'subdomain', 'record_type', 'ip', name='uq_cache_key'),)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_session() -> Session:
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# Resolver ops

def list_resolvers() -> List[str]:
    with get_session() as s:
        return [r.ip for r in s.query(Resolver).all()]


def add_resolver(ip: str) -> None:
    with get_session() as s:
        if not s.query(Resolver).filter(Resolver.ip == ip).first():
            s.add(Resolver(ip=ip))


def remove_resolver(ip: str) -> bool:
    with get_session() as s:
        r = s.query(Resolver).filter(Resolver.ip == ip).first()
        if r:
            s.delete(r)
            return True
        return False


# Domain and subdomain ops

def _normalize_ips(ip_value) -> str:
    if isinstance(ip_value, list):
        return ",".join([str(i).strip() for i in ip_value])
    return str(ip_value).strip() if ip_value is not None else None


def _present_ip_value(csv_ips: Optional[str]) -> Optional[Union[str, List[str]]]:
    if csv_ips is None or csv_ips == "":
        return None
    parts = [p.strip() for p in str(csv_ips).split(',') if p.strip() != ""]
    if len(parts) <= 1:
        return parts[0] if parts else None
    return parts


def get_domains_config() -> Dict[str, Dict]:
    """Return structure compatible with previous JSON config: { domain: { ip, subdomains: {name: ip|[ips]}} }.
    If multiple comma-separated IPs exist, return a list[str]; otherwise a single string."""
    with get_session() as s:
        result: Dict[str, Dict] = {}
        for d in s.query(Domain).all():
            sub_map: Dict[str, Union[str, List[str]]] = {}
            for sub in d.subdomains:
                sub_map[sub.name] = _present_ip_value(sub.ip)
            result[d.name] = {"ip": _present_ip_value(d.ip), "subdomains": sub_map}
        return result


def upsert_domain(domain: str, ip, subdomains: Optional[Dict[str, str]] = None) -> None:
    with get_session() as s:
        d = s.query(Domain).filter(Domain.name == domain).first()
        norm_ip = _normalize_ips(ip)
        if d is None:
            d = Domain(name=domain, ip=norm_ip)
            s.add(d)
            s.flush()
        else:
            d.ip = norm_ip
        if subdomains:
            for sub_name, sub_ip in subdomains.items():
                existing = s.query(Subdomain).filter(Subdomain.domain_id == d.id, Subdomain.name == sub_name).first()
                if existing:
                    existing.ip = _normalize_ips(sub_ip)
                else:
                    s.add(Subdomain(domain_id=d.id, name=sub_name, ip=_normalize_ips(sub_ip)))


def delete_domain(domain: str) -> bool:
    with get_session() as s:
        d = s.query(Domain).filter(Domain.name == domain).first()
        if d:
            s.delete(d)
            return True
        return False


def upsert_subdomain(domain: str, subdomain: str, ip) -> None:
    with get_session() as s:
        d = s.query(Domain).filter(Domain.name == domain).first()
        if d is None:
            d = Domain(name=domain, ip=None)
            s.add(d)
            s.flush()
        existing = s.query(Subdomain).filter(Subdomain.domain_id == d.id, Subdomain.name == subdomain).first()
        if existing:
            existing.ip = _normalize_ips(ip)
        else:
            s.add(Subdomain(domain_id=d.id, name=subdomain, ip=_normalize_ips(ip)))


def remove_subdomain(domain: str, subdomain: str) -> bool:
    with get_session() as s:
        d = s.query(Domain).filter(Domain.name == domain).first()
        if not d:
            return False
        sd = s.query(Subdomain).filter(Subdomain.domain_id == d.id, Subdomain.name == subdomain).first()
        if sd:
            s.delete(sd)
            return True
        return False


# Cache ops

def cache_clear() -> None:
    with get_session() as s:
        s.query(CacheEntry).delete()


def cache_get_ips(domain: str, subdomain: Optional[str], record_type: str) -> List[str]:
    with get_session() as s:
        q = s.query(CacheEntry.ip).filter(CacheEntry.domain == domain, CacheEntry.record_type == record_type)
        if subdomain:
            q = q.filter(CacheEntry.subdomain == subdomain)
        else:
            q = q.filter(CacheEntry.subdomain.is_(None))
        return [row[0] for row in q.all()]


def cache_store_ips(domain: str, subdomain: Optional[str], record_type: str, ips: List[str]) -> None:
    import time as _time
    now = int(_time.time())
    with get_session() as s:
        q = s.query(CacheEntry).filter(CacheEntry.domain == domain, CacheEntry.record_type == record_type)
        if subdomain:
            q = q.filter(CacheEntry.subdomain == subdomain)
        else:
            q = q.filter(CacheEntry.subdomain.is_(None))
        q.delete()
        for ip in ips:
            s.add(CacheEntry(domain=domain, subdomain=subdomain, record_type=record_type, ip=str(ip), timestamp=now))


def cache_check_valid(domain: str, subdomain: Optional[str], record_type: str, ttl_seconds: Optional[int] = None) -> bool:
    import time as _time
    ttl = CACHE_TTL_SECONDS_DEFAULT if ttl_seconds is None else max(int(ttl_seconds), 120)
    cutoff = int(_time.time()) - ttl
    with get_session() as s:
        q = s.query(func.min(CacheEntry.timestamp)).filter(CacheEntry.domain == domain, CacheEntry.record_type == record_type)
        if subdomain:
            q = q.filter(CacheEntry.subdomain == subdomain)
        else:
            q = q.filter(CacheEntry.subdomain.is_(None))
        row = q.first()
        oldest_ts = row[0] if row else None
        logging.debug(f"Cache check: domain='{domain}' subdomain='{subdomain}' type='{record_type}' oldest_ts={oldest_ts} cutoff={cutoff} ttl={ttl}")
        if oldest_ts is None:
            logging.debug("Cache miss: no entries for key")
            return False
        if oldest_ts <= cutoff:
            purge_q = s.query(CacheEntry).filter(CacheEntry.domain == domain, CacheEntry.record_type == record_type)
            if subdomain:
                purge_q = purge_q.filter(CacheEntry.subdomain == subdomain)
            else:
                purge_q = purge_q.filter(CacheEntry.subdomain.is_(None))
            purge_q.delete()
            logging.debug("Cache expired: purged entries for key")
            return False
        logging.debug("Cache valid: using cached entries")
        return True


def get_full_config() -> Dict:
    return {
        "resolvers": list_resolvers() or ["8.8.8.8"],
        "domains": get_domains_config()
    }
