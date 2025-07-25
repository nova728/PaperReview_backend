#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Automatic Review Service - 集成Automatic_Review项目的功能
"""

import json
import logging
import os
import sys
from typing import Dict, List, Optional, Any
from pathlib import Path

# 添加Automatic_Review路径到sys.path
automatic_review_path = Path(__file__).parent.parent.parent / "Automatic_Review"
if automatic_review_path.exists():
    sys.path.append(str(automatic_review_path))

logger = logging.getLogger(__name__)

class AutomaticReviewService:
    """自动评审服务 - 集成Automatic_Review项目的功能"""
    
    def __init__(self, config, vllm_service=None):
        self.config = config
        self.vllm_service = vllm_service
        self.automatic_review_path = automatic_review_path
        self.evaluation_path = automatic_review_path / "evaluation"
        self.generation_path = automatic_review_path / "generation"
        
        # 检查Automatic_Review项目是否存在
        if not automatic_review_path.exists():
            logger.warning("Automatic_Review项目不存在，某些功能可能不可用")
    
    def generate_review(self, paper_content: str) -> Dict[str, Any]:
        """
        生成评审 - 使用Automatic_Review的原始功能
        
        Args:
            paper_content: 论文内容
            
        Returns:
            包含评审结果的字典
        """
        try:
            return self._generate_review_using_automatic_review(paper_content)
        except Exception as e:
            logger.error(f"生成评审失败: {str(e)}")
            return {"error": str(e)}
    
    def _generate_review_using_automatic_review(self, paper_content: str) -> Dict[str, Any]:
        """使用Automatic_Review的原始功能生成评审"""
        # 使用Automatic_Review的prompt模板
        prompt_template = self._load_prompt_template("generation", "prompt_generate_review_v2.txt")
        
        # 在<paper>标签处插入论文内容
        prompt = prompt_template + paper_content + "\n</paper>"
        
        # 调用LLM生成评审
        review_content = self._call_llm_for_review(prompt)
        
        return {
            "type": "automatic_review",
            "content": review_content,
            "source": "Automatic_Review"
        }
    
    def classify_review_aspects(self, review_text: str) -> List[str]:
        """
        对评审文本进行方面分类
        
        Args:
            review_text: 评审文本
            
        Returns:
            分类的方面列表
        """
        try:
            # 加载方面分类prompt
            aspect_prompt = self._load_prompt_template("evaluation", "prompt_aspect_classicification.txt")
            
            if not aspect_prompt:
                # 使用简化的分类逻辑
                return self._simple_aspect_classification(review_text)
            
            # 构建分类请求
            classification_prompt = aspect_prompt.replace("<claim>", review_text)
            
            # 调用LLM进行分类
            result = self._call_llm_for_classification(classification_prompt)
            
            # 解析JSON结果
            try:
                parsed_result = json.loads(result)
                return parsed_result.get("aspects", [])
            except json.JSONDecodeError:
                logger.warning("无法解析分类结果JSON，使用简单分类")
                return self._simple_aspect_classification(review_text)
                
        except Exception as e:
            logger.error(f"方面分类失败: {str(e)}")
            return []
    
    def _simple_aspect_classification(self, review_text: str) -> List[str]:
        """简单的方面分类（基于关键词匹配）"""
        aspect_keywords = {
            "Novelty": ["novel", "novelty", "original", "innovative", "new"],
            "Contribution of the research": ["contribution", "contributes", "contributed"],
            "Algorithm Performance": ["performance", "accuracy", "efficiency", "speed"],
            "Clarity and Presentation": ["clear", "clarity", "presentation", "writing"],
            "Theoretical Soundness": ["theoretical", "theory", "soundness", "methodology"],
            "Experimental Validation": ["experiment", "validation", "results", "evaluation"],
            "Comparison to Previous Studies": ["comparison", "previous", "existing", "baseline"],
            "Reproducibility": ["reproducibility", "reproducible", "implementation"]
        }
        
        matched_aspects = []
        review_lower = review_text.lower()
        
        for aspect, keywords in aspect_keywords.items():
            if any(keyword in review_lower for keyword in keywords):
                matched_aspects.append(aspect)
        
        return matched_aspects
    
    def _load_prompt_template(self, module: str, filename: str) -> Optional[str]:
        """加载提示词模板"""
        try:
            if module == "generation":
                prompt_path = self.generation_path / "prompts" / filename
            elif module == "evaluation":
                prompt_path = self.evaluation_path / "prompts" / filename
            else:
                return None
            
            if prompt_path.exists():
                with open(prompt_path, 'r', encoding='utf-8') as f:
                    return f.read()
            else:
                logger.warning(f"提示词模板文件不存在: {prompt_path}")
                return None
                
        except Exception as e:
            logger.error(f"加载提示词模板失败: {str(e)}")
            return None
    
    def _call_llm_for_review(self, prompt: str) -> str:
        """调用LLM生成评审"""
        if self.vllm_service:
            try:
                # 使用VllmService
                return self.vllm_service.generate_peer_review(
                    paper_content="",  
                    query=prompt,
                    temperature=0.0,  # 确定性输出
                    max_tokens=8192 
                )
            except Exception as e:
                logger.error(f"调用VllmService失败: {str(e)}")
                return f"Error generating review: {str(e)}"
        else:
            # 如果没有VllmService，返回占位符
            return "This is a placeholder review content. Please provide VllmService for actual LLM call."
    
    def _call_llm_for_classification(self, prompt: str) -> str:
        """调用LLM进行分类"""
        if self.vllm_service:
            try:
                # 使用现有的VllmService进行分类
                return self.vllm_service.generate_peer_review(
                    paper_content="",  # 这里paper_content已经在prompt中了
                    query=prompt,
                    temperature=0.0, 
                    max_tokens=1024  
                )
            except Exception as e:
                logger.error(f"调用VllmService进行分类失败: {str(e)}")
                return '{"aspects": ["Novelty", "Contribution of the research"]}'
        else:
            # 如果没有VllmService，返回默认分类
            return '{"aspects": ["Novelty", "Contribution of the research"]}'
    
    def evaluate_review_quality(self, review_text: str, reference_review: str = None) -> Dict[str, float]:
        """
        评估评审质量
        
        Args:
            review_text: 待评估的评审文本
            reference_review: 参考评审文本（可选）
            
        Returns:
            质量评估分数
        """
        try:
            # 这里可以集成Automatic_Review的评估逻辑
            # 暂时返回占位符分数
            return {
                "overall_score": 0.75,
                "completeness": 0.8,
                "objectivity": 0.7,
                "constructiveness": 0.8
            }
        except Exception as e:
            logger.error(f"评估评审质量失败: {str(e)}")
            return {"error": str(e)} 