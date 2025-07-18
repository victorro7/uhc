"""
Configuration management for hackathon review system.
"""
import os
from typing import Optional
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class GitHubConfig:
    """GitHub API configuration."""
    token: Optional[str]
    base_url: str = "https://api.github.com"
    timeout: int = 30
    max_retries: int = 3
    rate_limit_delay: float = 1.0


@dataclass
class AnalysisConfig:
    """Analysis configuration and thresholds."""
    large_commit_threshold: int = 500 
    suspicious_file_count: int = 5
    max_commits_per_minute: int = 3
    reference_code_file: Optional[str] = "main_test.py"
    similarity_high_threshold: float = 0.8
    similarity_medium_threshold: float = 0.6


class ConfigManager:
    """Manages application configuration."""
    
    def __init__(self):
        self.github = self._load_github_config()
        self.analysis = self._load_analysis_config()
    
    def _load_github_config(self) -> GitHubConfig:
        """Load GitHub configuration from environment."""
        return GitHubConfig(
            token=os.getenv("GITHUB_TOKEN"),
            base_url=os.getenv("GITHUB_BASE_URL", "https://api.github.com"),
            timeout=int(os.getenv("GITHUB_TIMEOUT", "30")),
            max_retries=int(os.getenv("GITHUB_MAX_RETRIES", "3")),
            rate_limit_delay=float(os.getenv("GITHUB_RATE_LIMIT_DELAY", "1.0"))
        )
    
    def _load_analysis_config(self) -> AnalysisConfig:
        """Load analysis configuration from environment."""
        return AnalysisConfig(
            large_commit_threshold=int(os.getenv("LARGE_COMMIT_THRESHOLD", "500")),
            suspicious_file_count=int(os.getenv("SUSPICIOUS_FILE_COUNT", "5")),
            max_commits_per_minute=int(os.getenv("MAX_COMMITS_PER_MINUTE", "3")),
            reference_code_file=os.getenv("REFERENCE_CODE_FILE", "main_test.py"),
            similarity_high_threshold=float(os.getenv("SIMILARITY_HIGH_THRESHOLD", "0.8")),
            similarity_medium_threshold=float(os.getenv("SIMILARITY_MEDIUM_THRESHOLD", "0.6"))
        )
    
    def validate(self) -> list:
        """Validate configuration and return any errors."""
        errors = []
        
        if not self.github.token:
            errors.append("GITHUB_TOKEN environment variable is required for API access")
        
        if self.analysis.large_commit_threshold <= 0:
            errors.append("Large commit threshold must be positive")
        
        if self.analysis.suspicious_file_count <= 0:
            errors.append("Suspicious file count must be positive")
        
        if self.analysis.max_commits_per_minute <= 0:
            errors.append("Max commits per minute must be positive")
        
        return errors


config = ConfigManager() 