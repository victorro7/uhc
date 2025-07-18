# HackUMBC Commit History Analysis System

## Features

### 🔍 **Violation Detection**
- **Timing Violations**: Commits outside hackathon timeframe
- **Large Initial Commits**: Suspicious code drops at project start
- **Unauthorized Contributors**: Contributors not on team roster
- **Code Reuse**: Similarity detection against reference codebases
- **Suspicious Patterns**: Rapid commit bursts and identical timestamps
- **Team Size Violations**: Excessive number of contributors

### ⚙️ **Configurable Analysis**
- **Custom Reference Files**: Compare against any codebase
- **Adjustable Thresholds**: Fine-tune sensitivity settings
- **Environment Variables**: Easy deployment configuration
- **Comprehensive Logging**: Detailed analysis output

## Installation

### Prerequisites
- Python
- GitHub API token (for repository access)

### Setup
1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd uhc
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**
   ```bash
   cp env_template.txt .env
   # Edit .env with your settings
   ```

## Usage

### Basic Analysis
```bash
python main.py
```

### Custom Reference File
```bash
python main.py --reference-file suspicious_code.py
```

### Full Options
```bash
python main.py \
  --teams-csv src/data/teams.csv \
  --reference-file main_test.py \
```

## Configuration

### Environment Variables
```bash
# GitHub API
GITHUB_TOKEN=your_token_here
GITHUB_BASE_URL=https://api.github.com
GITHUB_TIMEOUT=30

# Analysis Thresholds
LARGE_COMMIT_THRESHOLD=500
SUSPICIOUS_FILE_COUNT=5
MAX_COMMITS_PER_MINUTE=3

# Code Comparison
REFERENCE_CODE_FILE=main_test.py
SIMILARITY_HIGH_THRESHOLD=0.8
SIMILARITY_MEDIUM_THRESHOLD=0.6
```

### Hackathon Configuration
Edit `config/hackathon_config.py`:
```python
HACKATHON_NAME = "HackUMBC 2026"
HACKATHON_START_TIME = datetime(2026, 9, 25, 9, 0, 0, tzinfo=timezone(timedelta(hours=-4)))
HACKATHON_END_TIME = datetime(2026, 9, 26, 12, 0, 0, tzinfo=timezone(timedelta(hours=-4)))
MAX_TEAM_SIZE = 4
GRACE_PERIOD_HOURS = 2
```

## Team Data Format

Create a CSV file with team information:
```csv
team_id,team_name,member_name,github_username,email,repository_url,devpost_url
team_001,useRaven Team,Victor Rodriguez,victorro7,victor@gmail.com,https://github.com/victorro7/useRaven,
team_002,SimilaritySeek Team,Bray Nguyen,braynguyen,bray@gmail.com,https://github.com/braynguyen/SimilaritySeek,
```

## Violation Types

### 🕐 **Timing Violations**
- **Early Commits**: Code committed before hackathon start
- **Late Commits**: Code committed after deadline + grace period
- **Severity**: Based on commit size and count

### 📁 **Large Initial Commits**
- **Threshold**: Configurable line count (default: 500 lines)
- **Detection**: First commits with suspicious amounts of code
- **Indicators**: Potential pre-existing codebase

### 👥 **Unauthorized Contributors**
- **Team Roster**: Cross-reference with registered members
- **GitHub Activity**: Analyze commit authors and contributors
- **Impact Assessment**: Measure unauthorized contribution volume

### 🔄 **Code Reuse**
- **Reference Comparison**: Similarity detection against provided files
- **Thresholds**: 
  - High similarity: 80%+ (severe violation)
  - Medium similarity: 60-80% (moderate violation)
- **Hash Matching**: Exact copy detection

### ⚡ **Suspicious Patterns**
- **Rapid Commits**: Multiple commits within minutes
- **Identical Timestamps**: Potential batch uploads
- **Pattern Analysis**: Statistical anomaly detection

## Output

### Console Analysis Summary
- **Team Statistics**: Total, clean, and flagged teams
- **Success Rate**: Percentage of teams passing all checks
- **Violation Counts**: Detailed breakdown by team
- **Progress Tracking**: Real-time analysis updates

### Log Files
```
hackathon_analysis.log    # Detailed analysis log
```

## Architecture

### Core Components
```
src/
├── core/
│   ├── models.py          # Data models and types
│   ├── config.py          # Configuration management
│   ├── github_client.py   # GitHub API integration
│   ├── analyzer.py        # Violation detection engine
│   ├── code_comparison.py # Code similarity analysis
│   └── team_loader.py     # CSV data loading
└── data/
    └── teams.csv          # Team data
```

### Configuration
```
config/
└── hackathon_config.py    # Hackathon-specific settings
```

### Custom Reference Files
The system supports any text based reference file for code comparison:
- **Programming Languages**: Python, JavaScript, Java, C++, etc.
- **Configuration Files**: JSON, YAML, XML
- **Documentation**: Markdown, text files