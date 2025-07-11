from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, Float
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class Torrent(Base):
    __tablename__ = "torrents"
    
    id = Column(String, primary_key=True)
    hash = Column(String(40), nullable=False, index=True)
    filename = Column(String, nullable=False)
    status = Column(String, nullable=False, index=True)
    size = Column(Integer, default=0)
    added_date = Column(DateTime, nullable=False)
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)
    attempts_count = Column(Integer, default=0)
    last_attempt = Column(DateTime)
    last_success = Column(DateTime)
    priority = Column(Integer, default=2)
    needs_cleanup = Column(Boolean, default=False)


class Attempt(Base):
    __tablename__ = "attempts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    torrent_id = Column(String, nullable=False, index=True)
    attempt_date = Column(DateTime, default=datetime.utcnow)
    success = Column(Boolean, nullable=False)
    error_message = Column(Text)
    response_time_ms = Column(Integer)
    api_response = Column(Text)


class BrokenSymlink(Base):
    __tablename__ = "broken_symlinks"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    source_path = Column(String, nullable=False)
    target_path = Column(String, nullable=False)
    torrent_name = Column(String, nullable=False)
    status = Column(String, nullable=False)
    size = Column(Integer, default=0)
    detected_date = Column(DateTime, default=datetime.utcnow)
    matched_torrent_id = Column(String)
    processed = Column(Boolean, default=False)


class ScanProgress(Base):
    __tablename__ = "scan_progress"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_type = Column(String, nullable=False)  # 'api', 'symlinks'
    current_offset = Column(Integer, default=0)
    total_expected = Column(Integer, default=0)
    last_scan_start = Column(DateTime)
    last_scan_complete = Column(DateTime)
    status = Column(String, default='idle')  # 'idle', 'running', 'completed'


