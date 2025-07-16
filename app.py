from flask import Flask, request, jsonify
from flask_cors import CORS
from config.config import AppConfig
from services.text_processor_service import TextProcessorService
from services.vllm_service import VllmService
from models.paper_models import PaperRequest, PaperResponse
import logging
import time
from datetime import datetime

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__)
    
    # JSON配置
    app.config['JSON_AS_ASCII'] = False  
    app.config['JSON_Sort_KEYS'] = False
    app.json.ensure_ascii = False
    
    CORS(app)
    
    # 初始化服务
    config = AppConfig()
    text_processor = TextProcessorService()
    vllm_service = VllmService(config)
    
    @app.route('/api/papers/health', methods=['GET'])
    def health():
        """健康检查接口"""
        return jsonify({"message": "Paper Review Backend is running!"}), 200
    
    @app.route('/api/papers/peer-review', methods=['POST'])
    def generate_peer_review():
        """生成paper review接口"""
        try:
            # 获取请求数据
            data = request.get_json()
            paper_request = PaperRequest.from_dict(data)
            
            logger.info(f"收到同行评审请求")
            
            start_time = time.time()

            # 获取论文内容
            paper_content = text_processor.process_paper_json(paper_request.paper_json)
            logger.info("使用JSON格式论文数据")
            
            # 同行评审prompt
            review_query = """Please provide a comprehensive peer review of this academic paper. Focus on the following aspects:
                1. Novelty and significance of the contribution
                2. Technical quality and soundness of the methodology
                3. Clarity of writing and presentation
                4. Experimental validation and results analysis
                5. Related work coverage and comparison
                6. Limitations and potential improvements
                Please provide detailed comments and recommendations."""
            
            # 处理文本长度
            use_chunking = data.get('use_chunking', True)
            original_length = len(paper_content)
            
            if use_chunking and original_length > text_processor.MAX_LENGTH:
                logger.info(f"文本长度 {original_length} 超过限制 {text_processor.MAX_LENGTH}, 启用分块处理")
                # 分块处理
                peer_review = text_processor.process_long_text_with_chunks(
                    paper_content, 
                    review_query,
                    vllm_service
                )
                processing_method = "chunk_processing"
            else:
                logger.info(f"文本长度 {original_length} 在限制内, 使用普通处理")
                # 普通处理
                peer_review = vllm_service.generate_peer_review(
                    paper_content, 
                    review_query,
                    temperature=paper_request.temperature,
                    max_tokens=paper_request.max_tokens
                )
                processing_method = "normal_processing"
            
            end_time = time.time()
            processing_time = end_time - start_time
            
            # 构建响应
            response = PaperResponse(
                success=True,
                response=peer_review,
                timestamp=datetime.now(),
                stats={
                    'input_length': original_length,
                    'output_length': len(peer_review),
                    'processing_time': processing_time,
                    'processing_method': processing_method,
                    'max_length_limit': text_processor.MAX_LENGTH,
                    'chunk_size': text_processor.CHUNK_SIZE if processing_method == "chunk_processing" else None,
                    'used_chunking': use_chunking,
                    'review_type': 'peer_review'
                }
            )
            
            logger.info(f"同行评审生成完成, 处理方法: {processing_method}")
            return jsonify(response.to_dict()), 200
            
        except Exception as e:
            logger.error(f"同行评审生成失败: {str(e)}")
            error_response = PaperResponse(
                success=False,
                error=str(e),
                timestamp=datetime.now()
            )
            return jsonify(error_response.to_dict()), 500
    
    @app.route('/api/papers/test-vllm', methods=['GET'])
    def test_vllm():
        """测试vLLM连接"""
        try:
            result = vllm_service.generate_peer_review(
                "This is a test document about machine learning research.",
                "Please briefly review this document"
            )
            return jsonify({"message": f"vLLM连接正常: {result}"}), 200
        except Exception as e:
            return jsonify({"error": f"vLLM连接失败: {str(e)}"}), 500
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=8080, debug=True)
