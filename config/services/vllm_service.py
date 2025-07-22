import requests
import logging
import json
from typing import Optional, Generator
from config.config import AppConfig
from models.vllm_models import VllmRequest, VllmMessage, VllmResponse

logger = logging.getLogger(__name__)

class VllmService:
    def __init__(self, config: AppConfig):
        self.config = config
        self.base_url = config.vllm.base_url.rstrip('/')
        self._warmup_model()
        
    def generate_peer_review(self, paper_content: str, query: str, 
                            temperature: float = 0.7, max_tokens: int = 2048) -> str:
        """Generate peer review"""
        logger.info("Calling vLLM to generate peer review")
        
        try:
            # 构建prompt
            prompt = self._build_peer_review_prompt(paper_content, query)
            
            # 创建请求
            vllm_request = VllmRequest(
                model=self.config.vllm.model_name,
                messages=[
                    VllmMessage(role="system", content="You are a professional academic peer reviewer with expertise in evaluating research papers."),
                    VllmMessage(role="user", content=prompt)
                ],
                max_tokens=max_tokens,
                temperature=temperature
            )
            
            # 调用API
            response = self._call_vllm_api(vllm_request)
            content = response.get_content()
            
            if not content.strip():
                raise RuntimeError("vLLM 服务返回空结果")
                
            logger.info(f"vLLM peer review 生成完成，输出长度: {len(content)} 字符")
            return content
            
        except Exception as e:
            logger.error(f"vLLM 调用失败: {str(e)}")
            raise RuntimeError(f"论文总结生成失败: {str(e)}")
    
    def generate_peer_review_stream(self, paper_content: str, query: str, 
                                   temperature: float = 0.7, max_tokens: int = 2048) -> Generator[str, None, None]:
        """Generate peer review with streaming output"""
        logger.info("Calling vLLM to generate peer review (streaming)")
        
        try:
            # 构建prompt
            prompt = self._build_peer_review_prompt(paper_content, query)
            
            # 创建流式请求
            vllm_request = VllmRequest(
                model=self.config.vllm.model_name,
                messages=[
                    VllmMessage(role="system", content="You are a professional academic peer reviewer with expertise in evaluating research papers."),
                    VllmMessage(role="user", content=prompt)
                ],
                max_tokens=max_tokens,
                temperature=temperature,
                stream=True
            )
            
            # 调用流式API
            for chunk in self._call_vllm_stream_api(vllm_request):
                yield chunk
            
            logger.info("vLLM peer review streaming completed")
            
        except Exception as e:
            logger.error(f"vLLM 流式调用失败: {str(e)}")
            raise RuntimeError(f"论文总结流式生成失败: {str(e)}")
    
    def _build_peer_review_prompt(self, paper_content: str, query: str) -> str:
        """构建prompt"""
        max_length = self.config.vllm.max_context_length
        limited_content = paper_content[:max_length] + "..." if len(paper_content) > max_length else paper_content
        
        prompt = f"""You are conducting a peer review of an academic paper. Please read the paper carefully and provide a comprehensive evaluation.

Paper Content:
{limited_content}

Review Focus: {query}

Please provide a thorough peer review covering the following aspects:
1. **Novelty and Significance**: Evaluate the originality and importance of the research contributions
2. **Technical Quality**: Assess the methodology, experimental design, and technical soundness
3. **Clarity and Presentation**: Comment on the writing quality, organization, and clarity
4. **Experimental Validation**: Evaluate the experiments, results, and their interpretation
5. **Related Work**: Assess how well the paper positions itself relative to existing literature
6. **Limitations and Future Work**: Identify any limitations and suggestions for improvement

Requirements: Provide a detailed, constructive, and professional peer review response."""
        
        return prompt
    
    def _call_vllm_api(self, vllm_request: VllmRequest) -> VllmResponse:
        """调用API"""
        url = f"{self.base_url}/v1/chat/completions"
        
        try:
            response = requests.post(
                url,
                json=vllm_request.to_dict(),
                timeout=self.config.vllm.timeout,
                headers={'Content-Type': 'application/json'}
            )
            response.raise_for_status()
            
            return VllmResponse.from_dict(response.json())
            
        except requests.exceptions.RequestException as e:
            logger.error(f"vLLM API 调用失败: {str(e)}")
            raise RuntimeError(f"vLLM API 调用失败: {str(e)}")

    def _call_vllm_stream_api(self, vllm_request: VllmRequest) -> Generator[str, None, None]:
        """调用流式API"""
        url = f"{self.base_url}/v1/chat/completions"
        
        try:
            response = requests.post(
                url,
                json=vllm_request.to_dict(),
                timeout=self.config.vllm.timeout,
                headers={'Content-Type': 'application/json'},
                stream=True
            )
            response.raise_for_status()
            
            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    if line.startswith('data: '):
                        data_content = line[6:]  # 移除 'data: ' 前缀
                        
                        if data_content.strip() == '[DONE]':
                            break
                            
                        try:
                            chunk_data = json.loads(data_content)
                            choices = chunk_data.get('choices', [])
                            if choices and len(choices) > 0:
                                delta = choices[0].get('delta', {})
                                content = delta.get('content', '')
                                if content:
                                    yield content
                        except json.JSONDecodeError:
                            # 忽略无法解析的行
                            continue
            
        except requests.exceptions.RequestException as e:
            logger.error(f"vLLM 流式API 调用失败: {str(e)}")
            raise RuntimeError(f"vLLM 流式API 调用失败: {str(e)}")

    def _warmup_model(self):
        """预热模型"""
        try:
            logger.info("正在预热vLLM模型...")
            dummy_request = VllmRequest(
                model=self.config.vllm.model_name,
                messages=[
                    VllmMessage(role="system", content="You are an AI assistant."),
                    VllmMessage(role="user", content="test")
                ],
                max_tokens=10,
                temperature=0.1
            )
            self._call_vllm_api(dummy_request)
            logger.info("vLLM模型预热完成")
        except Exception as e:
            logger.warning(f"模型预热失败，但服务仍可正常运行: {str(e)}")
