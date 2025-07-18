"""
Code comparison system for detecting code reuse against reference files.
"""
import hashlib
import logging
import re
from typing import List, Dict
from difflib import SequenceMatcher
from pathlib import Path

from .models import Violation, ViolationType

logger = logging.getLogger(__name__)


class CodeComparisonEngine:
    """Engine for detecting code reuse against a configurable reference file."""
    
    def __init__(self, reference_file_path: str, high_threshold: float = 0.8, medium_threshold: float = 0.6):
        self.reference_file_path = reference_file_path
        self.high_threshold = high_threshold
        self.medium_threshold = medium_threshold
        self.reference_content = ""
        self.reference_hash = ""
        self.load_reference_code()
    
    def load_reference_code(self):
        """Load reference code from the specified file."""
        try:
            with open(self.reference_file_path, 'r', encoding='utf-8') as f:
                self.reference_content = f.read()
                self.reference_hash = self._calculate_file_hash(self.reference_content)
            logger.info(f"Loaded reference code from {self.reference_file_path} ({len(self.reference_content)} chars)")
        except FileNotFoundError:
            logger.warning(f"Reference file {self.reference_file_path} not found - skipping code comparison")
            self.reference_content = ""
        except Exception as e:
            logger.error(f"Failed to load reference file {self.reference_file_path}: {e}")
            self.reference_content = ""
    
    def analyze_code_files(self, repo_files: List[Dict], team_name: str) -> List[Violation]:
        """Analyze repository files against the configured reference file."""
        violations = []
        
        if not repo_files or not self.reference_content:
            return violations
        
        logger.info(f"Comparing {len(repo_files)} code files against reference {self.reference_file_path}")
        
        for file_info in repo_files:
            file_violations = self._compare_against_reference(file_info, team_name)
            violations.extend(file_violations)
        
        return violations
    
    def _compare_against_reference(self, file_info: Dict, team_name: str) -> List[Violation]:
        """Compare a single file against the reference file."""
        violations = []
        file_path = file_info['path']
        content = file_info['content']
        
        similarity = self._calculate_similarity(content, self.reference_content)
        
        if similarity > self.high_threshold:
            violations.append(Violation(
                type=ViolationType.CODE_REUSE,
                severity="high",
                description=f"High similarity ({similarity:.1%}) to reference code in {file_path}",
                evidence={
                    "file_path": file_path,
                    "similarity_score": similarity,
                    "reference_file": self.reference_file_path,
                    "match_type": "high_similarity",
                    "file_size": len(content),
                    "reference_size": len(self.reference_content)
                }
            ))
        elif similarity > self.medium_threshold:
            violations.append(Violation(
                type=ViolationType.CODE_REUSE,
                severity="medium",
                description=f"Moderate similarity ({similarity:.1%}) to reference code in {file_path}",
                evidence={
                    "file_path": file_path,
                    "similarity_score": similarity,
                    "reference_file": self.reference_file_path,
                    "match_type": "moderate_similarity",
                    "file_size": len(content),
                    "reference_size": len(self.reference_content)
                }
            ))
        
        file_hash = self._calculate_file_hash(content)
        if file_hash == self.reference_hash:
            violations.append(Violation(
                type=ViolationType.CODE_REUSE,
                severity="high",
                description=f"Exact copy of reference code detected in {file_path}",
                evidence={
                    "file_path": file_path,
                    "match_type": "exact_copy",
                    "file_hash": file_hash,
                    "reference_file": self.reference_file_path
                }
            ))
        
        block_matches = self._find_matching_code_blocks(content, self.reference_content)
        if block_matches > 2:
            violations.append(Violation(
                type=ViolationType.CODE_REUSE,
                severity="medium",
                description=f"Multiple code blocks ({block_matches}) match reference in {file_path}",
                evidence={
                    "file_path": file_path,
                    "matching_blocks": block_matches,
                    "reference_file": self.reference_file_path,
                    "match_type": "code_blocks"
                }
            ))
        
        return violations
    
    def _calculate_similarity(self, content1: str, content2: str) -> float:
        """Calculate similarity between two code files."""
        norm1 = self._normalize_code(content1)
        norm2 = self._normalize_code(content2)
        
        matcher = SequenceMatcher(None, norm1, norm2)
        return matcher.ratio()
    
    def _normalize_code(self, content: str) -> str:
        """Normalize code for comparison."""
        content = re.sub(r'#.*?$', '', content, flags=re.MULTILINE)
        content = re.sub(r'//.*?$', '', content, flags=re.MULTILINE)
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        content = re.sub(r'""".*?"""', '', content, flags=re.DOTALL)
        content = re.sub(r"'''.*?'''", '', content, flags=re.DOTALL)
        
        content = re.sub(r'\s+', ' ', content)
        content = re.sub(r'^(import|from)\s+.*?$', '', content, flags=re.MULTILINE)
        
        return content.strip().lower()
    
    def _calculate_file_hash(self, content: str) -> str:
        """Calculate SHA-256 hash of normalized file content."""
        normalized = self._normalize_code(content)
        return hashlib.sha256(normalized.encode()).hexdigest()
    
    def _find_matching_code_blocks(self, content: str, reference: str) -> int:
        """Find number of matching code blocks between files."""
        content_blocks = self._extract_code_blocks(content)
        reference_blocks = self._extract_code_blocks(reference)
        
        matches = 0
        for block1 in content_blocks:
            for block2 in reference_blocks:
                similarity = self._calculate_similarity(block1, block2)
                if similarity > 0.7:
                    matches += 1
                    break
        
        return matches
    
    def _extract_code_blocks(self, content: str) -> List[str]:
        """Extract logical code blocks from content."""
        blocks = []
        lines = content.split('\n')
        current_block = []
        in_function = False
        indent_level = 0
        
        for line in lines:
            stripped = line.strip()
            
            if stripped.startswith(('def ', 'class ', 'async def ')):
                if current_block and in_function:
                    blocks.append('\n'.join(current_block))
                current_block = [line]
                in_function = True
                indent_level = len(line) - len(line.lstrip())
            elif in_function:
                line_indent = len(line) - len(line.lstrip())
                if line_indent > indent_level or not stripped:
                    current_block.append(line)
                else:
                    blocks.append('\n'.join(current_block))
                    current_block = []
                    in_function = False
        
        if current_block and in_function:
            blocks.append('\n'.join(current_block))
        
        return [block for block in blocks if len(block.strip()) > 50] 