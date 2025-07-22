from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from config.config import AppConfig
from services.text_processor_service import TextProcessorService
from services.vllm_service import VllmService
from models.paper_models import PaperRequest, PaperResponse
import logging
import time
import json
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
    vllm_service = VllmService(config)
    
    @app.route('/api/papers/health', methods=['GET'])
    def health():
        """健康检查接口"""
        return jsonify({"message": "Paper Review Backend is running!"}), 200
    
    @app.route('/api/papers/peer-review', methods=['POST'])
    def generate_peer_review():
        """生成paper review接口 - 支持流式和非流式输出"""
        try:
            # 获取请求数据
            data = request.get_json()
            paper_request = PaperRequest.from_dict(data)
            
            # 检查是否请求流式输出
            stream_output = data.get('stream', False)
            
            logger.info(f"收到同行评审请求，流式输出: {stream_output}")
            
            start_time = time.time()

            # 根据请求参数创建文本处理器
            text_processor = TextProcessorService(include_authors=paper_request.include_authors)
            
            # 获取完整论文内容（不截断）用于分块判断
            full_paper_content = text_processor.process_paper_json(paper_request.paper_json, auto_truncate=False)
            original_length = len(full_paper_content)
            
            logger.info(f"使用JSON格式论文数据，包含作者信息: {paper_request.include_authors}")
            logger.info(f"完整文本长度: {original_length:,} 字符")
            
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
            
            if stream_output:
                # 流式输出
                return Response(
                    stream_peer_review_generator(
                        full_paper_content, 
                        review_query, 
                        paper_request,
                        vllm_service,
                        use_chunking,
                        original_length,
                        start_time
                    ),
                    mimetype='text/event-stream',
                    headers={
                        'Cache-Control': 'no-cache',
                        'Connection': 'keep-alive',
                        'Access-Control-Allow-Origin': '*',
                        'Access-Control-Allow-Headers': 'Content-Type'
                    }
                )
            else:
                # 非流式输出（保持原有逻辑）
                if use_chunking and original_length > text_processor.MAX_LENGTH:
                    logger.info(f"文本长度 {original_length} 超过限制 {text_processor.MAX_LENGTH}, 启用分块处理")
                    # 分块处理，使用完整文本
                    peer_review = text_processor.process_long_text_with_chunks(
                        full_paper_content, 
                        review_query,
                        vllm_service
                    )
                    processing_method = "chunk_processing"
                else:
                    logger.info(f"文本长度 {original_length} 在限制内, 使用普通处理")
                    # 普通处理，截断文本以符合长度限制
                    truncated_content = text_processor._truncate_to_max_length(full_paper_content)
                    peer_review = vllm_service.generate_peer_review(
                        truncated_content, 
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
            if stream_output:
                # 流式错误响应
                def error_generator():
                    error_data = {
                        'type': 'error',
                        'success': False,
                        'error': str(e),
                        'timestamp': datetime.now().isoformat()
                    }
                    yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
                
                return Response(
                    error_generator(),
                    mimetype='text/event-stream',
                    headers={
                        'Cache-Control': 'no-cache',
                        'Connection': 'keep-alive',
                        'Access-Control-Allow-Origin': '*',
                        'Access-Control-Allow-Headers': 'Content-Type'
                    }
                )
            else:
                # 非流式错误响应
                error_response = PaperResponse(
                    success=False,
                    error=str(e),
                    timestamp=datetime.now()
                )
                return jsonify(error_response.to_dict()), 500
    
    def stream_peer_review_generator(full_paper_content, review_query, paper_request, 
                                   vllm_service, use_chunking, 
                                   original_length, start_time):
        """流式peer review生成器"""
        try:
            # 重新创建文本处理器
            text_processor = TextProcessorService(include_authors=paper_request.include_authors)
            
            # 发送开始事件
            start_data = {
                'type': 'start',
                'message': '开始生成同行评审',
                'stats': {
                    'input_length': original_length,
                    'use_chunking': use_chunking,
                    'max_length_limit': text_processor.MAX_LENGTH
                }
            }
            yield f"data: {json.dumps(start_data, ensure_ascii=False)}\n\n"
            
            # 确定处理方法
            if use_chunking and original_length > text_processor.MAX_LENGTH:
                processing_method = "chunk_processing_stream"
                logger.info(f"文本长度 {original_length} 超过限制, 启用流式分块处理")
                
                # 流式分块处理
                content_chunks = []
                for chunk in text_processor.process_long_text_with_chunks_stream(
                    full_paper_content, 
                    review_query, 
                    vllm_service
                ):
                    content_chunks.append(chunk)
                    chunk_data = {
                        'type': 'content',
                        'content': chunk
                    }
                    yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"
                
                full_content = ''.join(content_chunks)
            else:
                processing_method = "normal_processing_stream"
                logger.info(f"文本长度 {original_length} 在限制内, 使用流式普通处理")
                
                # 流式普通处理，先截断文本
                truncated_content = text_processor._truncate_to_max_length(full_paper_content)
                content_chunks = []
                for chunk in vllm_service.generate_peer_review_stream(
                    truncated_content, 
                    review_query,
                    temperature=paper_request.temperature,
                    max_tokens=paper_request.max_tokens
                ):
                    content_chunks.append(chunk)
                    chunk_data = {
                        'type': 'content',
                        'content': chunk
                    }
                    yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"
                
                full_content = ''.join(content_chunks)
            
            # 发送完成事件
            end_time = time.time()
            processing_time = end_time - start_time
            
            end_data = {
                'type': 'end',
                'success': True,
                'message': '同行评审生成完成',
                'stats': {
                    'input_length': original_length,
                    'output_length': len(full_content),
                    'processing_time': processing_time,
                    'processing_method': processing_method,
                    'max_length_limit': text_processor.MAX_LENGTH,
                    'chunk_size': text_processor.CHUNK_SIZE if "chunk" in processing_method else None,
                    'used_chunking': use_chunking,
                    'review_type': 'peer_review'
                }
            }
            yield f"data: {json.dumps(end_data, ensure_ascii=False)}\n\n"
            
            logger.info(f"流式同行评审生成完成, 处理方法: {processing_method}")
            
        except Exception as e:
            logger.error(f"流式同行评审生成失败: {str(e)}")
            error_data = {
                'type': 'error',
                'success': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
            yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
    
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
