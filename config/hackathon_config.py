"""
Hackathon configuration settings.
"""
from datetime import datetime, timezone, timedelta

# Hackathon configuration
HACKATHON_NAME = "HackUMBC 2026"
HACKATHON_START_TIME = datetime(2026, 9, 25, 9, 0, 0, tzinfo=timezone(timedelta(hours=-4)))
HACKATHON_END_TIME = datetime(2026, 9, 26, 12, 0, 0, tzinfo=timezone(timedelta(hours=-4)))
MAX_TEAM_SIZE = 4
GRACE_PERIOD_HOURS = 2
LARGE_COMMIT_THRESHOLD = 1000

# File paths
TEAMS_CSV_FILE = "src/data/teams.csv" 