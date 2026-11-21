"""SQLAlchemy models (SQLite now; types chosen to stay PostgreSQL-compatible)."""
from datetime import datetime, timezone

from sqlalchemy import (JSON, Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()
now = lambda: datetime.now(timezone.utc)


class SchemaMigration(Base):
    __tablename__ = "schema_migrations"
    version = Column(Integer, primary_key=True)
    applied_at = Column(DateTime, default=now)


class Company(Base):
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    sector = Column(String(100))
    industry = Column(String(150))
    created_at = Column(DateTime, default=now)
    symbols = relationship("ExchangeSymbol", back_populates="company")


class ExchangeSymbol(Base):
    __tablename__ = "exchange_symbols"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    exchange = Column(String(8), nullable=False)
    symbol = Column(String(24), nullable=False)
    company = relationship("Company", back_populates="symbols")
    __table_args__ = (UniqueConstraint("exchange", "symbol", name="uq_exchange_symbol"),)


class MarketPrice(Base):
    __tablename__ = "market_prices"
    id = Column(Integer, primary_key=True)
    symbol_id = Column(Integer, ForeignKey("exchange_symbols.id"), nullable=False)
    trade_date = Column(DateTime, nullable=False)
    interval = Column(String(8), default="1d")
    open, high, low, close, volume = (Column(Float) for _ in range(5))
    source = Column(String(40), nullable=False)
    fetched_at = Column(DateTime, default=now)
    __table_args__ = (UniqueConstraint("symbol_id", "trade_date", "interval", "source", name="uq_price"),
                      Index("ix_price_symbol_date", "symbol_id", "trade_date"))


class FinancialStatement(Base):
    """One row per (statement, period, source, content). Changed restatements are inserted as NEW rows; history is never overwritten."""
    __tablename__ = "financial_statements"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    statement_type = Column(String(30), nullable=False)
    period_type = Column(String(10), nullable=False)
    period_end = Column(DateTime, nullable=False)
    source = Column(String(40), nullable=False)
    content_hash = Column(String(64), nullable=False)
    payload = Column(JSON, nullable=False)
    fetched_at = Column(DateTime, default=now)
    __table_args__ = (UniqueConstraint("company_id", "statement_type", "period_type", "period_end", "source", "content_hash", name="uq_statement"),
                      Index("ix_stmt_company_period", "company_id", "period_end"))


class NewsArticle(Base):
    __tablename__ = "news_articles"
    id = Column(Integer, primary_key=True)
    symbol_id = Column(Integer, ForeignKey("exchange_symbols.id"), nullable=False)
    headline = Column(Text, nullable=False)
    source = Column(String(120))
    published_at = Column(String(40))
    url = Column(Text)
    sentiment = Column(String(12))
    relevance = Column(String(12))
    verification_status = Column(String(30))
    title_key = Column(String(130), nullable=False)
    __table_args__ = (UniqueConstraint("symbol_id", "title_key", name="uq_news"),)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id = Column(Integer, primary_key=True)
    run_id = Column(String(40), nullable=False, index=True)
    symbol = Column(String(24), nullable=False)
    exchange = Column(String(8), nullable=False)
    agent = Column(String(30), nullable=False)
    status = Column(String(10), nullable=False)
    error = Column(Text)
    started_at = Column(String(40))
    finished_at = Column(String(40))
    created_at = Column(DateTime, default=now)


class AgentOutput(Base):
    __tablename__ = "agent_outputs"
    id = Column(Integer, primary_key=True)
    agent_run_id = Column(Integer, ForeignKey("agent_runs.id"), nullable=False)
    payload = Column(JSON, nullable=False)


class ResearchScore(Base):
    __tablename__ = "research_scores"
    id = Column(Integer, primary_key=True)
    run_id = Column(String(40), nullable=False, index=True)
    symbol = Column(String(24), nullable=False)
    exchange = Column(String(8), nullable=False)
    created_at = Column(DateTime, default=now, index=True)
    fundamental, technical, data_confidence, risk = (Column(Float) for _ in range(4))
    long_term, short_term, balanced = (Column(Float) for _ in range(3))
    risk_class = Column(String(12))
    tags = Column(JSON)
    is_synthetic = Column(Boolean, default=False)
    __table_args__ = (Index("ix_score_symbol_created", "symbol", "exchange", "created_at"),)


class RiskFinding(Base):
    __tablename__ = "risk_findings"
    id = Column(Integer, primary_key=True)
    run_id = Column(String(40), nullable=False, index=True)
    symbol = Column(String(24), nullable=False)
    category = Column(String(40))
    severity = Column(String(10))
    title = Column(Text)
    evidence = Column(Text)
    as_of = Column(String(20))
    verified = Column(Boolean)


class ResearchReport(Base):
    __tablename__ = "research_reports"
    id = Column(Integer, primary_key=True)
    run_id = Column(String(40), nullable=False, index=True)
    symbol = Column(String(24), nullable=False)
    exchange = Column(String(8), nullable=False)
    fmt = Column(String(8), nullable=False)
    path = Column(Text, nullable=False)
    created_at = Column(DateTime, default=now)


class DataSource(Base):
    __tablename__ = "data_sources"
    id = Column(Integer, primary_key=True)
    name = Column(String(40), unique=True, nullable=False)
    description = Column(Text)
    last_success_at = Column(DateTime)
    last_error = Column(Text)
    last_error_at = Column(DateTime)


class DataQualityLog(Base):
    __tablename__ = "data_quality_logs"
    id = Column(Integer, primary_key=True)
    run_id = Column(String(40), index=True)
    symbol = Column(String(24))
    provider = Column(String(40))
    level = Column(String(10))
    message = Column(Text)
    created_at = Column(DateTime, default=now)


class Watchlist(Base):
    __tablename__ = "watchlists"
    id = Column(Integer, primary_key=True)
    symbol = Column(String(24), nullable=False)
    exchange = Column(String(8), nullable=False)
    enabled = Column(Boolean, default=True)
    note = Column(Text)
    added_at = Column(DateTime, default=now)
    __table_args__ = (UniqueConstraint("symbol", "exchange", name="uq_watch"),)


class Alert(Base):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True)
    symbol = Column(String(24), nullable=False)
    exchange = Column(String(8), nullable=False)
    kind = Column(String(30), nullable=False)  # score_change | risk_escalation | agent_failure | critical_risk
    severity = Column(String(10), nullable=False)
    message = Column(Text, nullable=False)
    run_id = Column(String(40))
    created_at = Column(DateTime, default=now, index=True)
    acknowledged = Column(Boolean, default=False)


class PipelineRun(Base):
    """One execution of the daily research pipeline (scheduled or manual)."""
    __tablename__ = "pipeline_runs"
    id = Column(Integer, primary_key=True)
    trigger = Column(String(12), nullable=False)  # scheduled | manual
    status = Column(String(12), default="running")  # running | complete | partial | failed
    started_at = Column(DateTime, default=now)
    finished_at = Column(DateTime)
    cycle_id = Column(Integer)
    summary = Column(JSON)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key = Column(String(60), primary_key=True)
    value = Column(Text)


class FloorActivity(Base):
    """Every floor reports here; Floor 00 reads it. to_floor marks a hand-off between floors."""
    __tablename__ = "floor_activity"
    id = Column(Integer, primary_key=True)
    floor = Column(Integer, nullable=False)
    to_floor = Column(Integer)
    event = Column(String(40), nullable=False)
    status = Column(String(8), default="ok")  # ok | error | info
    message = Column(Text)
    payload = Column(JSON)
    run_id = Column(String(40))
    created_at = Column(DateTime, default=now)
    __table_args__ = (Index("ix_activity_floor_time", "floor", "created_at"),)


class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True)
    kind = Column(String(30), nullable=False)
    payload = Column(JSON)
    status = Column(String(10), default="queued", index=True)  # queued | running | done | failed
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=3)
    last_error = Column(Text)
    created_at = Column(DateTime, default=now)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)


class UniverseStock(Base):
    __tablename__ = "universe"
    id = Column(Integer, primary_key=True)
    exchange = Column(String(8), nullable=False)
    symbol = Column(String(24), nullable=False)  # NSE: ticker; BSE: numeric scrip code (Yahoo uses code.BO)
    alt_symbol = Column(String(40))
    name = Column(String(200))
    isin = Column(String(16), index=True)
    series = Column(String(10))
    listing_status = Column(String(20), default="Active")
    source = Column(String(80), nullable=False)
    imported_at = Column(DateTime, default=now)
    __table_args__ = (UniqueConstraint("exchange", "symbol", name="uq_universe"),)


class ScanCycle(Base):
    __tablename__ = "scan_cycles"
    id = Column(Integer, primary_key=True)
    status = Column(String(10), default="running")  # running | complete
    started_at = Column(DateTime, default=now)
    finished_at = Column(DateTime)
    total = Column(Integer, default=0)


class ScanItem(Base):
    """Per-stock progress inside a cycle. state = process state; coverage = how much real data we obtained."""
    __tablename__ = "scan_items"
    id = Column(Integer, primary_key=True)
    cycle_id = Column(Integer, ForeignKey("scan_cycles.id"), nullable=False)
    exchange = Column(String(8), nullable=False)
    symbol = Column(String(24), nullable=False)
    name = Column(String(200))
    state = Column(String(10), default="pending", index=True)  # pending | done | failed
    coverage = Column(String(12))  # complete | partial | unavailable (None until attempted)
    stage = Column(String(6))  # light | deep
    attempts = Column(Integer, default=0)
    error = Column(Text)
    data_date = Column(String(12))  # date of the last price bar used
    light_score = Column(Float)  # technical score from the price-only scan
    momentum_3m = Column(Float)
    avg_traded_value = Column(Float)
    liquidity_class = Column(String(10))
    run_id = Column(String(40))
    updated_at = Column(DateTime, default=now)
    __table_args__ = (UniqueConstraint("cycle_id", "exchange", "symbol", name="uq_scan_item"),
                      Index("ix_scan_cycle_state", "cycle_id", "state"))


class Decision(Base):
    __tablename__ = "decisions"
    id = Column(Integer, primary_key=True)
    run_id = Column(String(40), nullable=False, index=True)
    symbol = Column(String(24), nullable=False)
    exchange = Column(String(8), nullable=False)
    verdict = Column(String(10), nullable=False)  # APPROVE | REJECT | WATCHLIST
    reasons = Column(JSON)
    risk_assessment = Column(JSON)
    balanced = Column(Float)
    fundamental, technical, data_confidence, risk = (Column(Float) for _ in range(4))
    risk_class = Column(String(12))
    created_at = Column(DateTime, default=now, index=True)


class PaperAccount(Base):
    __tablename__ = "paper_account"
    id = Column(Integer, primary_key=True)
    starting_capital = Column(Float, nullable=False)
    cash = Column(Float, nullable=False)
    created_at = Column(DateTime, default=now)


class PaperOrder(Base):
    """SIMULATED order. Fills use the last known (delayed) close, never a live exchange price."""
    __tablename__ = "paper_orders"
    id = Column(Integer, primary_key=True)
    symbol = Column(String(24), nullable=False)
    exchange = Column(String(8), nullable=False)
    side = Column(String(4), nullable=False)
    qty = Column(Integer, nullable=False)
    ref_price = Column(Float, nullable=False)
    ref_price_date = Column(String(12))
    fill_price = Column(Float)
    status = Column(String(10), default="FILLED")  # FILLED | REJECTED
    reason = Column(Text)
    simulated = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)


class PaperPosition(Base):
    __tablename__ = "paper_positions"
    id = Column(Integer, primary_key=True)
    symbol = Column(String(24), nullable=False)
    exchange = Column(String(8), nullable=False)
    sector = Column(String(100))
    qty = Column(Integer, nullable=False)
    entry_price = Column(Float, nullable=False)
    stop_loss = Column(Float)
    target = Column(Float)
    status = Column(String(8), default="OPEN", index=True)  # OPEN | CLOSED
    opened_at = Column(DateTime, default=now)
    closed_at = Column(DateTime)
    exit_price = Column(Float)
    exit_reason = Column(String(20))  # STOP | TARGET | MANUAL
    realized_pnl = Column(Float)


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"
    id = Column(Integer, primary_key=True)
    taken_at = Column(DateTime, default=now, index=True)
    equity = Column(Float, nullable=False)
    cash = Column(Float, nullable=False)
    positions_value = Column(Float, nullable=False)


class PriceAlertRule(Base):
    __tablename__ = "price_alert_rules"
    id = Column(Integer, primary_key=True)
    symbol = Column(String(24), nullable=False)
    exchange = Column(String(8), nullable=False)
    direction = Column(String(5), nullable=False)  # above | below
    price = Column(Float, nullable=False)
    active = Column(Boolean, default=True)
    triggered_at = Column(DateTime)
