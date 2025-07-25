from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from config.config import AppConfig
from services.text_processor_service import TextProcessorService
from services.vllm_service import VllmService
from services.automatic_review_service import AutomaticReviewService
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
    automatic_review_service = AutomaticReviewService(config, vllm_service)
    
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
            # 移除分块相关参数
            
            if stream_output:
                # 流式输出
                return Response(
                    stream_peer_review_generator(
                        full_paper_content, 
                        review_query, 
                        paper_request,
                        vllm_service,
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
                # 非流式输出（截断处理）
                logger.info(f"文本长度 {original_length}, 使用截断处理")
                # 截断文本以符合长度限制
                truncated_content = text_processor._truncate_to_max_tokens(full_paper_content)
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
                        'max_tokens_limit': text_processor.MAX_TOKENS,
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
                                   vllm_service, 
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
                    'max_tokens_limit': text_processor.MAX_TOKENS
                }
            }
            yield f"data: {json.dumps(start_data, ensure_ascii=False)}\n\n"
            
            # 流式处理（截断处理）
            processing_method = "stream_processing"
            logger.info(f"文本长度 {original_length}, 使用流式截断处理")
            
            # 截断文本并进行流式处理
            truncated_content = text_processor._truncate_to_max_tokens(full_paper_content)
            content_chunks = []
            for chunk in vllm_service.generate_peer_review_stream(
                truncated_content, 
                review_query
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
                    'max_tokens_limit': text_processor.MAX_TOKENS,
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
    
    @app.route('/api/papers/automatic-review', methods=['POST'])
    def automatic_review():
        """自动评审接口 - 使用Automatic_Review原始功能，返回符合前端期望的格式"""
        try:
            # 获取请求数据
            data = request.get_json()
            paper_request = PaperRequest.from_dict(data)
            
            logger.info("收到Automatic_Review评审请求")
            
            start_time = time.time()
            
            # 根据请求参数创建文本处理器
            text_processor = TextProcessorService(include_authors=paper_request.include_authors)
            
            # 获取完整论文内容
            paper_content = text_processor.process_paper_json(paper_request.paper_json, auto_truncate=False)
            
            logger.info(f"论文内容长度: {len(paper_content):,} 字符")
            
            # 生成评审 - 使用Automatic_Review原始功能
            review_result = automatic_review_service.generate_review(paper_content=paper_content)
            
            # 如果评审成功，进行方面分类
            if "error" not in review_result:
                review_text = review_result.get("content", "")
                aspects = automatic_review_service.classify_review_aspects(review_text)
                review_result["aspects"] = aspects
                
                # 将评审内容按方面分解，符合前端期望的格式
                reviews = []
                
                # 如果有方面分类，按方面分解内容
                if aspects and len(aspects) > 0:
                    # 简单的按方面分解策略：将评审内容按段落分割
                    paragraphs = review_text.split('\n\n')
                    
                    # 为每个方面分配内容
                    for i, aspect in enumerate(aspects):
                        if i < len(paragraphs):
                            content = paragraphs[i].strip()
                        else:
                            # 如果段落不够，使用剩余内容
                            content = review_text.strip()
                        
                        reviews.append({
                            "name": aspect,
                            "content": content
                        })
                else:
                    # 如果没有方面分类，将整个评审作为一个方面
                    reviews.append({
                        "name": "Overall Review",
                        "content": review_text.strip()
                    })
                
                end_time = time.time()
                processing_time = end_time - start_time
                
                # 返回符合前端期望的格式
                return jsonify({ "reviews": reviews }), 200
            else:
                # 评审失败，返回错误信息
                end_time = time.time()
                processing_time = end_time - start_time
                
                return jsonify({
                    "reviews": [{
                        "name": "Error",
                        "content": f"评审生成失败: {review_result.get('error', '未知错误')}"
                    }]
                }), 200
            
        except Exception as e:
            logger.error(f"Automatic_Review评审失败: {str(e)}")
            return jsonify({
                "reviews": [{
                    "name": "Error",
                    "content": f"评审生成失败: {str(e)}"
                }]
            }), 200
    
    @app.route('/api/papers/review-aspects', methods=['POST'])
    def classify_review_aspects():
        """评审方面分类接口"""
        try:
            data = request.get_json()
            review_text = data.get('review_text', '')
            
            if not review_text:
                return jsonify({
                    "status": "error",
                    "message": "review_text is required"
                }), 400
            
            # 进行方面分类
            aspects = automatic_review_service.classify_review_aspects(review_text)
            
            return jsonify({
                "status": "success",
                "aspects": aspects,
                "review_text_length": len(review_text)
            }), 200
            
        except Exception as e:
            logger.error(f"方面分类失败: {str(e)}")
            return jsonify({
                "status": "error",
                "message": f"Aspect classification failed: {str(e)}"
            }), 500
    
    @app.route('/api/papers/review-quality', methods=['POST'])
    def evaluate_review_quality():
        """评审质量评估接口"""
        try:
            data = request.get_json()
            review_text = data.get('review_text', '')
            reference_review = data.get('reference_review', None)
            
            if not review_text:
                return jsonify({
                    "status": "error",
                    "message": "review_text is required"
                }), 400
            
            # 评估评审质量
            quality_scores = automatic_review_service.evaluate_review_quality(
                review_text=review_text,
                reference_review=reference_review
            )
            
            return jsonify({
                "status": "success",
                "quality_scores": quality_scores,
                "review_text_length": len(review_text)
            }), 200
            
        except Exception as e:
            logger.error(f"质量评估失败: {str(e)}")
            return jsonify({
                "status": "error",
                "message": f"Quality evaluation failed: {str(e)}"
            }), 500
    
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
