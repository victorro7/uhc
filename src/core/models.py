"""
Data models for hackathon commit history review system.
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, HttpUrl, field_validator
from enum import Enum


class ViolationType(str, Enum):
    """Types of hackathon rule violations."""
    COMMITS_OUTSIDE_WINDOW = "commits_outside_window"
    UNAUTHORIZED_CONTRIBUTORS = "unauthorized_contributors"
    LARGE_INITIAL_COMMIT = "large_initial_commit"
    EXCESSIVE_CONTRIBUTORS = "excessive_contributors"
    SUSPICIOUS_TIMING = "suspicious_timing"
    CODE_REUSE = "code_reuse"


class TeamMember(BaseModel):
    """Represents a hackathon team member."""
    name: str
    github_username: str
    email: Optional[str] = None
    devpost_id: Optional[str] = None


class Team(BaseModel):
    """Represents a hackathon team."""
    team_id: str
    team_name: str
    members: List[TeamMember]
    devpost_url: Optional[HttpUrl] = None
    repository_url: HttpUrl
    
    @field_validator('members')
    @classmethod
    def validate_team_size(cls, v):
        if len(v) > 4:
            raise ValueError("Team size exceeds maximum allowed (4)")
        return v


class HackathonConfig(BaseModel):
    """Hackathon configuration and rules."""
    name: str
    start_time: datetime
    end_time: datetime
    max_team_size: int = 6
    grace_period_hours: int = 1
    large_commit_threshold: int = 1000
    
    @field_validator('end_time')
    @classmethod
    def validate_dates(cls, v, info):
        if 'start_time' in info.data and v <= info.data['start_time']:
            raise ValueError("End time must be after start time")
        return v


class CommitInfo(BaseModel):
    """Information about a git commit."""
    sha: str
    author: str
    author_email: str
    timestamp: datetime
    message: str
    additions: int
    deletions: int
    total_changes: int
    files_changed: int


class RepositoryInfo(BaseModel):
    """Information about a repository."""
    url: HttpUrl
    name: str
    owner: str
    created_at: datetime
    commits: List[CommitInfo]
    contributors: List[str]


class Violation(BaseModel):
    """Represents a detected violation."""
    type: ViolationType
    severity: str
    description: str
    evidence: Dict[str, Any]
    timestamp: Optional[datetime] = None


class TeamAnalysisResult(BaseModel):
    """Result of analyzing a team's repository."""
    team: Team
    repository_info: RepositoryInfo
    violations: List[Violation]
    is_flagged: bool
    summary: str
    analysis_timestamp: datetime
    
    @field_validator('is_flagged')
    @classmethod
    def determine_flagged_status(cls, v, info):
        if 'violations' in info.data:
            high_severity_violations = [
                violation for violation in info.data['violations'] 
                if violation.severity == "high"
            ]
            return len(high_severity_violations) > 0
        return False


class AnalysisReport(BaseModel):
    """Complete analysis report for all teams."""
    hackathon_config: HackathonConfig
    total_teams: int
    flagged_teams: int
    team_results: List[TeamAnalysisResult]
    generated_at: datetime
    summary_stats: Dict[str, int] 