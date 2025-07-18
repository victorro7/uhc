"""
Main script for hackathon commit history review system.
"""
import logging
import sys
import argparse
from pathlib import Path
from datetime import datetime
from typing import List
import traceback

from src.core.models import HackathonConfig, AnalysisReport, TeamAnalysisResult
from src.core.team_loader import CSVTeamLoader
from src.core.github_client import GitHubClient
from src.core.analyzer import CommitAnalyzer
from config.hackathon_config import (
    HACKATHON_NAME, HACKATHON_START_TIME, HACKATHON_END_TIME,
    MAX_TEAM_SIZE, GRACE_PERIOD_HOURS, LARGE_COMMIT_THRESHOLD,
    TEAMS_CSV_FILE
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("hackathon_analysis.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class HackathonAnalysisSystem:
    """Main system for hackathon analysis."""
    
    def __init__(self, teams_csv: str = None, reference_file: str = None):
        self.teams_csv = teams_csv or TEAMS_CSV_FILE
        self.reference_file = reference_file
        
        self.hackathon_config = HackathonConfig(
            name=HACKATHON_NAME,
            start_time=HACKATHON_START_TIME,
            end_time=HACKATHON_END_TIME,
            max_team_size=MAX_TEAM_SIZE,
            grace_period_hours=GRACE_PERIOD_HOURS,
            large_commit_threshold=LARGE_COMMIT_THRESHOLD
        )
        
        if self.reference_file:
            from src.core.config import config
            config.analysis.reference_code_file = self.reference_file
        
        self.github_client = GitHubClient()
        self.analyzer = CommitAnalyzer(self.hackathon_config, self.github_client)
        self.team_loader = CSVTeamLoader(self.teams_csv)
        
        self.successful_analyses = []
        self.failed_analyses = []
    
    def analyze_all_teams(self) -> AnalysisReport:
        """Analyze all teams from CSV and generate reports."""
        logger.info("🚀 Starting hackathon analysis")
        logger.info(f"Hackathon: {self.hackathon_config.name}")
        logger.info(f"Period: {self.hackathon_config.start_time} to {self.hackathon_config.end_time}")
        
        from src.core.config import config
        if config.analysis.reference_code_file:
            logger.info(f"Code comparison enabled against: {config.analysis.reference_code_file}")
        else:
            logger.info("Code comparison disabled (no reference file)")
        
        teams = self.team_loader.load_teams()
        logger.info(f"Loaded {len(teams)} teams from CSV")
        
        team_results = []
        for i, team_data in enumerate(teams):
            logger.info(f"📊 Analyzing team {i+1}/{len(teams)}: {team_data.team_name}")
            
            try:
                result = self._analyze_team(team_data)
                team_results.append(result)
                self.successful_analyses.append(team_data.team_name)
                
                status = "🚨 FLAGGED" if result.is_flagged else "✅ CLEAN"
                logger.info(f"   {status} - {len(result.violations)} violations")
                
                if result.violations:
                    violation_summary = {}
                    for violation in result.violations:
                        if violation.type.value not in violation_summary:
                            violation_summary[violation.type.value] = {"high": 0, "medium": 0, "low": 0}
                        violation_summary[violation.type.value][violation.severity] += 1
                    
                    for violation_type, severities in violation_summary.items():
                        total = sum(severities.values())
                        severity_breakdown = []
                        if severities["high"] > 0:
                            severity_breakdown.append(f"{severities['high']} high")
                        if severities["medium"] > 0:
                            severity_breakdown.append(f"{severities['medium']} medium")
                        if severities["low"] > 0:
                            severity_breakdown.append(f"{severities['low']} low")
                        
                        logger.info(f"     📋 {violation_type}: {total} ({', '.join(severity_breakdown)})")
                
            except Exception as e:
                logger.error(f"❌ Failed to analyze {team_data.team_name}: {e}")
                self.failed_analyses.append({
                    'team_name': team_data.team_name,
                    'error': str(e),
                    'url': team_data.repository_url
                })
                
                error_result = self._create_error_result(team_data, str(e))
                team_results.append(error_result)
        
        analysis_report = self._generate_analysis_report(team_results)
        
        logger.info(f"📈 Analysis complete!")
        logger.info(f"   Success: {len(self.successful_analyses)}")
        logger.info(f"   Failed: {len(self.failed_analyses)}")
        logger.info(f"   Results: {analysis_report.flagged_teams}/{analysis_report.total_teams} teams flagged")
        
        return analysis_report
    
    def _analyze_team(self, team_data) -> TeamAnalysisResult:
        """Analyze a single team."""
        team = self.team_loader.convert_to_team_model(team_data)
        
        logger.info(f"     Fetching repository data...")
        repo_info = self.github_client.analyze_repository(team_data.repository_url)
        
        logger.info(f"     Running violation analysis...")
        result = self.analyzer.analyze_team(team, repo_info)
        
        return result
    
    def _create_error_result(self, team_data, error_msg: str) -> TeamAnalysisResult:
        """Create error result for failed analysis."""
        from src.core.models import RepositoryInfo
        
        team = self.team_loader.convert_to_team_model(team_data)
        
        error_repo = RepositoryInfo(
            url=team_data.repository_url,
            name="ERROR",
            owner="ERROR",
            created_at=datetime.now(),
            commits=[],
            contributors=[]
        )
        
        return TeamAnalysisResult(
            team=team,
            repository_info=error_repo,
            violations=[],
            is_flagged=False,
            summary=f"Analysis failed: {error_msg}",
            analysis_timestamp=datetime.now()
        )
    
    def _generate_analysis_report(self, team_results: List[TeamAnalysisResult]) -> AnalysisReport:
        """Generate comprehensive analysis report."""
        from collections import Counter
        
        summary_stats = Counter()
        for result in team_results:
            for violation in result.violations:
                summary_stats[violation.type.value] += 1
        
        return AnalysisReport(
            hackathon_config=self.hackathon_config,
            total_teams=len(team_results),
            flagged_teams=sum(1 for result in team_results if result.is_flagged),
            team_results=team_results,
            generated_at=datetime.now(),
            summary_stats=dict(summary_stats)
        )


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="HackUMBC Commit History Analysis System"
    )
    parser.add_argument(
        "--teams-csv",
        type=str,
        default="src/data/teams.csv",
        help="CSV file with team data"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    parser.add_argument(
        "--reference-file",
        type=str,
        help="Reference code file to compare against (overrides config/env)"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    print("\n" + "="*60)
    print("🔍 HackUMBC Commit History Analysis System")
    print("="*60)
    
    try:
        system = HackathonAnalysisSystem(
            teams_csv=args.teams_csv,
            reference_file=args.reference_file
        )
        
        analysis_report = system.analyze_all_teams()
        
        print("\n" + "="*60)
        print("📊 ANALYSIS SUMMARY")
        print("="*60)
        print(f"📈 Total Teams: {analysis_report.total_teams}")
        print(f"✅ Clean Teams: {analysis_report.total_teams - analysis_report.flagged_teams}")
        print(f"🚨 Flagged Teams: {analysis_report.flagged_teams}")
        
        if analysis_report.flagged_teams > 0:
            success_rate = ((analysis_report.total_teams - analysis_report.flagged_teams) / analysis_report.total_teams * 100)
            print(f"📊 Success Rate: {success_rate:.1f}%")
            print(f"\n🔍 {analysis_report.flagged_teams} teams require manual review")
        else:
            print(f"🎉 All teams passed automated checks!")
        
        print("="*60)
        
    except KeyboardInterrupt:
        logger.info("⏸️  Analysis interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Analysis failed: {e}")
        if args.verbose:
            logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main() 