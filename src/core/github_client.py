"""
GitHub API client for repository analysis.
"""
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import config
from .models import RepositoryInfo, CommitInfo


logger = logging.getLogger(__name__)


class GitHubAPIError(Exception):
    """Custom exception for GitHub API errors."""
    pass


class GitHubClient:
    """GitHub API client with rate limiting and error handling."""
    
    def __init__(self):
        self.base_url = config.github.base_url
        self.token = config.github.token
        self.timeout = config.github.timeout
        self.max_retries = config.github.max_retries
        self.rate_limit_delay = config.github.rate_limit_delay
        
        self.session = requests.Session()
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        if self.token:
            self.session.headers.update({"Authorization": f"token {self.token}"})
    
    def parse_repo_url(self, repo_url: str) -> tuple[str, str]:
        """Parse GitHub repository URL to extract owner and repo name."""
        parsed = urlparse(repo_url)
        path_parts = parsed.path.strip('/').split('/')
        
        if len(path_parts) < 2:
            raise ValueError(f"Invalid GitHub repository URL: {repo_url}")
        
        owner = path_parts[0]
        repo = path_parts[1]
        
        if repo.endswith('.git'):
            repo = repo[:-4]
        
        return owner, repo
    
    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """Make a request to GitHub API with error handling."""
        url = f"{self.base_url}/{endpoint}"
        
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            
            if response.status_code == 429:
                reset_time = int(response.headers.get('X-RateLimit-Reset', time.time() + 60))
                sleep_time = reset_time - int(time.time()) + 1
                logger.warning(f"Rate limit hit. Sleeping for {sleep_time} seconds")
                time.sleep(sleep_time)
                return self._make_request(endpoint, params)
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"GitHub API request failed: {e}")
            raise GitHubAPIError(f"API request failed: {e}")
    
    def get_repository_info(self, repo_url: str) -> Dict:
        """Get basic repository information."""
        owner, repo = self.parse_repo_url(repo_url)
        return self._make_request(f"repos/{owner}/{repo}")
    
    def get_commits(self, repo_url: str, since: Optional[datetime] = None, until: Optional[datetime] = None) -> List[Dict]:
        """Get commits from repository."""
        owner, repo = self.parse_repo_url(repo_url)
        
        params = {"per_page": 100}
        if since:
            params["since"] = since.isoformat()
        if until:
            params["until"] = until.isoformat()
        
        commits = []
        page = 1
        
        while True:
            params["page"] = page
            page_commits = self._make_request(f"repos/{owner}/{repo}/commits", params)
            
            if not page_commits:
                break
                
            commits.extend(page_commits)
            
            if len(page_commits) < 100:
                break
                
            page += 1
            time.sleep(self.rate_limit_delay)
        
        return commits
    
    def get_contributors(self, repo_url: str) -> List[Dict]:
        """Get repository contributors."""
        owner, repo = self.parse_repo_url(repo_url)
        return self._make_request(f"repos/{owner}/{repo}/contributors")
    
    def get_commit_details(self, repo_url: str, commit_sha: str) -> Dict:
        """Get detailed commit information including files changed."""
        owner, repo = self.parse_repo_url(repo_url)
        return self._make_request(f"repos/{owner}/{repo}/commits/{commit_sha}")
    
    def _parse_datetime(self, date_str: str) -> datetime:
        """Parse GitHub datetime string to datetime object."""
        if date_str.endswith('Z'):
            date_str = date_str[:-1] + '+00:00'
        return datetime.fromisoformat(date_str)
    
    def analyze_repository(self, repo_url: str, since: Optional[datetime] = None, until: Optional[datetime] = None) -> RepositoryInfo:
        """Perform comprehensive repository analysis."""
        logger.info(f"Analyzing repository: {repo_url}")
        
        repo_info = self.get_repository_info(repo_url)
        commits_raw = self.get_commits(repo_url, since, until)
        contributors_raw = self.get_contributors(repo_url)
        
        commits = []
        for i, commit_data in enumerate(commits_raw[:20]):
            try:
                detailed_commit = self.get_commit_details(repo_url, commit_data['sha'])
                stats = detailed_commit.get('stats', {})
                files = detailed_commit.get('files', [])
                
                commit = CommitInfo(
                    sha=commit_data['sha'],
                    author=commit_data['commit']['author']['name'],
                    author_email=commit_data['commit']['author']['email'],
                    timestamp=self._parse_datetime(commit_data['commit']['author']['date']),
                    message=commit_data['commit']['message'],
                    additions=stats.get('additions', 0),
                    deletions=stats.get('deletions', 0),
                    total_changes=stats.get('additions', 0) + stats.get('deletions', 0),
                    files_changed=len(files)
                )
                commits.append(commit)
                time.sleep(0.1)
                
            except Exception as e:
                logger.warning(f"Failed to get detailed stats for commit {commit_data['sha'][:8]}: {e}")
                commit = CommitInfo(
                    sha=commit_data['sha'],
                    author=commit_data['commit']['author']['name'],
                    author_email=commit_data['commit']['author']['email'],
                    timestamp=self._parse_datetime(commit_data['commit']['author']['date']),
                    message=commit_data['commit']['message'],
                    additions=0,
                    deletions=0,
                    total_changes=0,
                    files_changed=0
                )
                commits.append(commit)
        
        if len(commits_raw) > 20:
            logger.info(f"Processing {len(commits_raw) - 20} additional commits without detailed stats")
            for commit_data in commits_raw[20:]:
                commit = CommitInfo(
                    sha=commit_data['sha'],
                    author=commit_data['commit']['author']['name'],
                    author_email=commit_data['commit']['author']['email'],
                    timestamp=self._parse_datetime(commit_data['commit']['author']['date']),
                    message=commit_data['commit']['message'],
                    additions=0,
                    deletions=0,
                    total_changes=0,
                    files_changed=0
                )
                commits.append(commit)
        
        contributors = [contributor['login'] for contributor in contributors_raw]
        
        return RepositoryInfo(
            url=repo_url,
            name=repo_info['name'],
            owner=repo_info['owner']['login'],
            created_at=self._parse_datetime(repo_info['created_at']),
            commits=commits,
            contributors=contributors
        ) 

    def get_repository_tree(self, repo_url: str) -> List[Dict]:
        """Get complete file tree of repository."""
        owner, repo = self.parse_repo_url(repo_url)
        repo_info = self.get_repository_info(repo_url)
        default_branch = repo_info['default_branch']
        return self._make_request(f"repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1")
    
    def get_file_content(self, repo_url: str, file_path: str) -> Dict:
        """Get content of a specific file."""
        owner, repo = self.parse_repo_url(repo_url)
        return self._make_request(f"repos/{owner}/{repo}/contents/{file_path}")
    
    def get_code_files(self, repo_url: str, max_files: int = 50) -> List[Dict]:
        """Get contents of code files from repository."""
        logger.info(f"Fetching code files from {repo_url}")
        
        code_extensions = {
            '.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.cpp', '.c', '.h', 
            '.cs', '.php', '.rb', '.go', '.rs', '.swift', '.kt', '.scala',
            '.html', '.css', '.scss', '.less', '.vue', '.svelte'
        }
        
        try:
            tree_data = self.get_repository_tree(repo_url)
            tree_items = tree_data.get('tree', [])
            
            code_files = []
            for item in tree_items:
                if item['type'] == 'blob':
                    file_path = item['path']
                    file_ext = '.' + file_path.split('.')[-1] if '.' in file_path else ''
                    
                    if file_ext.lower() in code_extensions:
                        if any(skip in file_path.lower() for skip in ['node_modules', '__pycache__', '.git', 'dist', 'build']):
                            continue
                        
                        code_files.append({
                            'path': file_path,
                            'sha': item['sha'],
                            'size': item.get('size', 0),
                            'url': item['url']
                        })
            
            code_files = code_files[:max_files]
            
            file_contents = []
            for file_info in code_files:
                try:
                    logger.info(f"  Fetching: {file_info['path']}")
                    content_data = self.get_file_content(repo_url, file_info['path'])
                    
                    import base64
                    if content_data.get('encoding') == 'base64':
                        try:
                            content = base64.b64decode(content_data['content']).decode('utf-8')
                            file_contents.append({
                                'path': file_info['path'],
                                'content': content,
                                'size': len(content),
                                'sha': file_info['sha'],
                                'lines': len(content.split('\n'))
                            })
                        except UnicodeDecodeError:
                            logger.warning(f"  Skipping binary file: {file_info['path']}")
                    
                    time.sleep(0.1)
                    
                except Exception as e:
                    logger.warning(f"  Failed to fetch {file_info['path']}: {e}")
                    continue
            
            logger.info(f"Successfully fetched {len(file_contents)} code files")
            return file_contents
            
        except Exception as e:
            logger.error(f"Failed to fetch code files from {repo_url}: {e}")
            return [] 