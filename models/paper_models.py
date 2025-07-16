from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any, List

@dataclass
class PaperRequest:
    paper_json: Dict[str, Any]  # JSON格式论文
    temperature: float = 0.7
    max_tokens: int = 2048
    use_chunking: bool = True  # 是否启用分块处理
    
    @classmethod
    def from_dict(cls, data: dict):
        # 检查是否提供了JSON格式的论文内容
        if not data.get('paper_json'):
            raise ValueError("必须提供 paper_json（JSON格式的论文数据）")
            
        return cls(
            paper_json=data['paper_json'],
            temperature=data.get('temperature', 0.7),
            max_tokens=data.get('max_tokens', 2048),
            use_chunking=data.get('use_chunking', True)
        )

@dataclass
class PaperResponse:
    success: bool
    timestamp: datetime
    response: Optional[str] = None
    error: Optional[str] = None
    stats: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> dict:
        return {
            'success': self.success,
            'timestamp': self.timestamp.isoformat(),
            'response': self.response,
            'error': self.error,
            'stats': self.stats
        }
