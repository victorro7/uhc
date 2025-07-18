"""
Team data loading from CSV files.
"""
import csv
from pathlib import Path
from typing import List, Dict, Optional
from collections import defaultdict
from dataclasses import dataclass
import logging

from .models import Team, TeamMember

logger = logging.getLogger(__name__)


@dataclass
class TeamData:
    """Team data loaded from CSV."""
    team_name: str
    team_id: str
    repository_url: str
    members: List[Dict[str, str]]
    devpost_url: Optional[str] = None


class CSVTeamLoader:
    """Load team data from CSV file."""
    
    def __init__(self, csv_file: str):
        self.csv_file = csv_file
    
    def load_teams(self) -> List[TeamData]:
        """Load teams from CSV file."""
        if not Path(self.csv_file).exists():
            raise FileNotFoundError(f"Teams CSV file not found: {self.csv_file}")
        
        teams_dict = defaultdict(lambda: {
            'team_name': '',
            'team_id': '',
            'repository_url': '',
            'members': [],
            'devpost_url': None
        })
        
        with open(self.csv_file, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                team_key = row['team_id']
                team_data = teams_dict[team_key]
                
                # Set team info (same for all members)
                team_data['team_name'] = row['team_name']
                team_data['team_id'] = row['team_id']
                team_data['repository_url'] = row['repository_url']
                if row['devpost_url'].strip():
                    team_data['devpost_url'] = row['devpost_url']
                
                # Add member
                team_data['members'].append({
                    'name': row['member_name'],
                    'github_username': row['github_username'],
                    'email': row['email']
                })
        
        # Convert to TeamData objects
        teams = []
        for team_data in teams_dict.values():
            teams.append(TeamData(
                team_name=team_data['team_name'],
                team_id=team_data['team_id'],
                repository_url=team_data['repository_url'],
                members=team_data['members'],
                devpost_url=team_data['devpost_url']
            ))
        
        logger.info(f"Loaded {len(teams)} teams from CSV")
        return teams
    
    def convert_to_team_model(self, team_data: TeamData) -> Team:
        """Convert TeamData to Team model."""
        team_members = [
            TeamMember(
                name=member["name"],
                github_username=member["github_username"],
                email=member["email"]
            )
            for member in team_data.members
        ]
        
        return Team(
            team_id=team_data.team_id,
            team_name=team_data.team_name,
            members=team_members,
            devpost_url=team_data.devpost_url,
            repository_url=team_data.repository_url
        ) 