"""
Commit analysis engine for detecting hackathon violations.
"""
import logging
from datetime import datetime, timedelta
from typing import List
from collections import Counter

from .config import config
from .models import (
    HackathonConfig, Team, TeamAnalysisResult, RepositoryInfo, 
    Violation, ViolationType
)
from .code_comparison import CodeComparisonEngine

logger = logging.getLogger(__name__)


class CommitAnalyzer:
    """Analyzes repository commits for hackathon rule violations."""
    
    def __init__(self, hackathon_config: HackathonConfig, github_client=None):
        self.hackathon_config = hackathon_config
        self.analysis_config = config.analysis
        self.github_client = github_client
        
        if self.analysis_config.reference_code_file:
            self.code_comparison_engine = CodeComparisonEngine(
                reference_file_path=self.analysis_config.reference_code_file,
                high_threshold=self.analysis_config.similarity_high_threshold,
                medium_threshold=self.analysis_config.similarity_medium_threshold
            )
        else:
            self.code_comparison_engine = None
    
    def analyze_team(self, team: Team, repository_info: RepositoryInfo) -> TeamAnalysisResult:
        """Analyze a team's repository for violations."""
        logger.info(f"Analyzing team: {team.team_name}")
        
        violations = []
        
        violations.extend(self._check_commit_timing(repository_info))
        violations.extend(self._check_unauthorized_contributors(team, repository_info))
        violations.extend(self._check_large_initial_commits(repository_info))
        violations.extend(self._check_excessive_contributors(team, repository_info))
        violations.extend(self._check_suspicious_patterns(repository_info))
        
        if self.github_client and self.code_comparison_engine:
            violations.extend(self._check_code_reuse(team, repository_info))
        
        summary = self._generate_summary(team, violations)
        
        return TeamAnalysisResult(
            team=team,
            repository_info=repository_info,
            violations=violations,
            is_flagged=any(v.severity == "high" for v in violations),
            summary=summary,
            analysis_timestamp=datetime.now()
        )
    
    def _check_commit_timing(self, repo_info: RepositoryInfo) -> List[Violation]:
        """Check for commits outside the hackathon timeframe."""
        violations = []
        
        grace_end = self.hackathon_config.end_time + timedelta(
            hours=self.hackathon_config.grace_period_hours
        )
        
        early_commits = []
        late_commits = []
        
        for commit in repo_info.commits:
            if commit.timestamp < self.hackathon_config.start_time:
                early_commits.append(commit)
            elif commit.timestamp > grace_end:
                late_commits.append(commit)
        
        if early_commits:
            severity = "high" if len(early_commits) > 5 or any(
                c.total_changes > 100 for c in early_commits
            ) else "medium"
            
            violations.append(Violation(
                type=ViolationType.COMMITS_OUTSIDE_WINDOW,
                severity=severity,
                description=f"Found {len(early_commits)} commits before hackathon start",
                evidence={
                    "early_commits": len(early_commits),
                    "total_changes_before": sum(c.total_changes for c in early_commits),
                    "commits": [
                        {
                            "sha": c.sha[:8],
                            "timestamp": c.timestamp.isoformat(),
                            "changes": c.total_changes,
                            "message": c.message[:100]
                        } for c in early_commits
                    ]
                }
            ))
        
        if late_commits:
            major_late_commits = [c for c in late_commits if c.total_changes > 50]
            severity = "high" if major_late_commits else "low"
            
            violations.append(Violation(
                type=ViolationType.COMMITS_OUTSIDE_WINDOW,
                severity=severity,
                description=f"Found {len(late_commits)} commits after deadline ({len(major_late_commits)} major)",
                evidence={
                    "late_commits": len(late_commits),
                    "major_late_commits": len(major_late_commits),
                    "commits": [
                        {
                            "sha": c.sha[:8],
                            "timestamp": c.timestamp.isoformat(),
                            "changes": c.total_changes,
                            "message": c.message[:100]
                        } for c in late_commits[:5]
                    ]
                }
            ))
        
        return violations
    
    def _check_unauthorized_contributors(self, team: Team, repo_info: RepositoryInfo) -> List[Violation]:
        """Check for contributors not on the team roster."""
        violations = []
        
        team_members = {member.github_username.lower() for member in team.members}
        repo_contributors = {username.lower() for username in repo_info.contributors}
        
        unauthorized = repo_contributors - team_members
        
        if unauthorized:
            unauthorized_commits = [
                commit for commit in repo_info.commits 
                if any(username in commit.author.lower() or username in commit.author_email.lower() 
                      for username in unauthorized)
            ]
            
            total_unauthorized_changes = sum(c.total_changes for c in unauthorized_commits)
            
            severity = "high" if total_unauthorized_changes > 100 else "medium"
            
            violations.append(Violation(
                type=ViolationType.UNAUTHORIZED_CONTRIBUTORS,
                severity=severity,
                description=f"Found {len(unauthorized)} unauthorized contributors",
                evidence={
                    "unauthorized_contributors": list(unauthorized),
                    "team_members": [m.github_username for m in team.members],
                    "unauthorized_commits": len(unauthorized_commits),
                    "unauthorized_changes": total_unauthorized_changes
                }
            ))
        
        return violations
    
    def _check_large_initial_commits(self, repo_info: RepositoryInfo) -> List[Violation]:
        """Check for suspiciously large initial commits."""
        violations = []
        
        if not repo_info.commits:
            return violations
        
        sorted_commits = sorted(repo_info.commits, key=lambda x: x.timestamp)
        initial_commits = sorted_commits
        
        for i, commit in enumerate(initial_commits):
            if (commit.total_changes > self.analysis_config.large_commit_threshold or 
                commit.files_changed > self.analysis_config.suspicious_file_count):
                
                severity = "high" if i == 0 else "medium" 
                
                violations.append(Violation(
                    type=ViolationType.LARGE_INITIAL_COMMIT,
                    severity=severity,
                    description=f"Large initial commit #{i+1}: {commit.total_changes} changes, {commit.files_changed} files",
                    evidence={
                        "commit_sha": commit.sha,
                        "commit_index": i,
                        "timestamp": commit.timestamp.isoformat(),
                        "total_changes": commit.total_changes,
                        "additions": commit.additions,
                        "deletions": commit.deletions,
                        "files_changed": commit.files_changed,
                        "message": commit.message,
                        "threshold": self.analysis_config.large_commit_threshold
                    }
                ))
        
        return violations
    
    def _check_excessive_contributors(self, team: Team, repo_info: RepositoryInfo) -> List[Violation]:
        """Check if repository has more contributors than team size allows."""
        violations = []
        
        max_contributors = self.hackathon_config.max_team_size
        actual_contributors = len(repo_info.contributors)
        
        if actual_contributors > max_contributors:
            violations.append(Violation(
                type=ViolationType.EXCESSIVE_CONTRIBUTORS,
                severity="high",
                description=f"Repository has {actual_contributors} contributors, max allowed is {max_contributors}",
                evidence={
                    "actual_contributors": actual_contributors,
                    "max_allowed": max_contributors,
                    "contributors": repo_info.contributors,
                    "team_size": len(team.members)
                }
            ))
        
        return violations
    
    def _check_code_reuse(self, team: Team, repo_info: RepositoryInfo) -> List[Violation]:
        """Check for code reuse and plagiarism."""
        violations = []
        
        try:
            repo_url_str = str(repo_info.url)
            code_files = self.github_client.get_code_files(repo_url_str, max_files=30)
            
            if not code_files:
                return violations
            
            code_violations = self.code_comparison_engine.analyze_code_files(code_files, team.team_name)
            violations.extend(code_violations)
                
        except Exception as e:
            logger.warning(f"Code reuse analysis failed: {e}")
        
        return violations
    
    def _check_suspicious_patterns(self, repo_info: RepositoryInfo) -> List[Violation]:
        """Check for suspicious commit patterns."""
        violations = []
        
        if not repo_info.commits:
            return violations
        
        violations.extend(self._check_rapid_commits(repo_info))
        violations.extend(self._check_identical_timestamps(repo_info))
        
        return violations
    
    def _check_rapid_commits(self, repo_info: RepositoryInfo) -> List[Violation]:
        """Check for suspiciously rapid commit patterns."""
        violations = []
        
        commit_windows = {}
        for commit in repo_info.commits:
            window = commit.timestamp.replace(second=0, microsecond=0)
            if window not in commit_windows:
                commit_windows[window] = []
            commit_windows[window].append(commit)
        
        for window, commits in commit_windows.items():
            if len(commits) > self.analysis_config.max_commits_per_minute:
                total_changes = sum(c.total_changes for c in commits)
                
                violations.append(Violation(
                    type=ViolationType.SUSPICIOUS_TIMING,
                    severity="medium",
                    description=f"Rapid commits: {len(commits)} commits in 1 minute at {window}",
                    evidence={
                        "timestamp": window.isoformat(),
                        "commit_count": len(commits),
                        "total_changes": total_changes,
                        "threshold": self.analysis_config.max_commits_per_minute
                    }
                ))
        
        return violations
    
    def _check_identical_timestamps(self, repo_info: RepositoryInfo) -> List[Violation]:
        """Check for commits with identical timestamps."""
        violations = []
        
        timestamp_counts = Counter(commit.timestamp for commit in repo_info.commits)
        
        identical_groups = [(ts, count) for ts, count in timestamp_counts.items() if count > 1]
        
        if identical_groups:
            total_identical = sum(count for _, count in identical_groups)
            
            violations.append(Violation(
                type=ViolationType.SUSPICIOUS_TIMING,
                severity="low",
                description=f"Found {len(identical_groups)} groups of commits with identical timestamps ({total_identical} total commits)",
                evidence={
                    "identical_groups": len(identical_groups),
                    "total_identical_commits": total_identical,
                    "examples": [
                        {"timestamp": ts.isoformat(), "count": count} 
                        for ts, count in identical_groups[:3]
                    ]
                }
            ))
        
        return violations
    
    def _generate_summary(self, team: Team, violations: List[Violation]) -> str:
        """Generate a summary of the analysis."""
        if not violations:
            return f"✅ Team '{team.team_name}' passed all checks - no violations detected."
        
        high_severity = [v for v in violations if v.severity == "high"]
        medium_severity = [v for v in violations if v.severity == "medium"]
        low_severity = [v for v in violations if v.severity == "low"]
        
        summary_parts = [f"🚨 Team '{team.team_name}' flagged with {len(violations)} violation(s):"]
        
        if high_severity:
            summary_parts.append(f"  🔴 HIGH ({len(high_severity)}): {', '.join(v.type.value for v in high_severity)}")
        
        if medium_severity:
            summary_parts.append(f"  🟡 MEDIUM ({len(medium_severity)}): {', '.join(v.type.value for v in medium_severity)}")
        
        if low_severity:
            summary_parts.append(f"  🟢 LOW ({len(low_severity)}): {', '.join(v.type.value for v in low_severity)}")
        
        return "\n".join(summary_parts) 