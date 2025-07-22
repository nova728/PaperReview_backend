#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 Hammer_review_backend 与 ScientificReviewer-7B 模型的集成
"""

import requests
import json
import time

def test_backend_health():
    """测试后端健康状态"""
    try:
        response = requests.get('http://localhost:5000/api/papers/health')
        if response.status_code == 200:
            print("✅ 后端服务正常运行")
            return True
        else:
            print(f"❌ 后端服务异常，状态码: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 无法连接到后端服务: {str(e)}")
        return False

def test_scientific_reviewer_request():
    """测试ScientificReviewer-7B请求格式"""
    
    # 构建测试请求
    test_request = {
        "paper_json": {
            "title": "Quantifying the Influence of Evaluation Aspects on Long-Form Response Assessment",
            "abstract": "Evaluating the outputs of large language models (LLMs) on long-form generative tasks remains challenging. While fine-grained, aspectwise evaluations provide valuable diagnostic information, they are difficult to design exhaustively, and each aspect's contribution to the overall acceptability of an answer is unclear. In this study, we propose a method to compute an overall quality score as a weighted average of three key aspects: factuality, informativeness, and formality. This approach achieves stronger correlations with human judgments compared to previous metrics. Our analysis identifies factuality as the most predictive aspect of overall quality. Additionally, we release a dataset of 1.2k long-form QA answers annotated with both absolute judgments and relative preferences in overall and aspect-wise schemes, to aid future research in evaluation practices."
        },
        "temperature": 0.7,
        "max_tokens": 1024,
        "use_chunking": True,
        "include_authors": False,
        "stream": False
    }
    
    try:
        print("🚀 测试ScientificReviewer-7B集成...")
        start_time = time.time()
        
        response = requests.post(
            'http://localhost:5000/api/papers/peer-review',
            headers={'Content-Type': 'application/json'},
            json=test_request,
            timeout=300
        )
        
        end_time = time.time()
        request_time = end_time - start_time
        
        print(f"⏱️  请求耗时: {request_time:.2f}秒")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ 集成测试成功！")
            print(f"📊 响应统计: {result.get('stats', {})}")
            
            if result.get('success'):
                review_content = result.get('response', '')
                print(f"📝 评审内容长度: {len(review_content)} 字符")
                print("📄 评审内容预览:")
                print("-" * 50)
                print(review_content[:500] + "..." if len(review_content) > 500 else review_content)
                print("-" * 50)
            else:
                print(f"❌ 请求失败: {result.get('error', '未知错误')}")
                
        else:
            print(f"❌ 请求失败，状态码: {response.status_code}")
            print("错误信息:", response.text)
            
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")

def test_direct_vllm_api():
    """直接测试vLLM API"""
    print("\n🔬 直接测试vLLM API...")
    
    direct_request = {
        "model": "scientific-reviewer-7b",
        "messages": [
            {
                "role": "user",
                "content": "请简单介绍一下你的功能。"
            }
        ],
        "temperature": 0.7,
        "max_tokens": 200
    }
    
    try:
        response = requests.post(
            'http://localhost:8000/v1/chat/completions',
            headers={'Content-Type': 'application/json'},
            json=direct_request,
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            content = result['choices'][0]['message']['content']
            print("✅ vLLM API直接测试成功:")
            print(content)
        else:
            print(f"❌ vLLM API测试失败: {response.status_code}")
            
    except Exception as e:
        print(f"❌ vLLM API测试错误: {str(e)}")

if __name__ == "__main__":
    print("🔬 Hammer_review_backend 集成测试")
    print("=" * 50)
    
    # 测试后端健康状态
    if test_backend_health():
        # 测试ScientificReviewer-7B集成
        test_scientific_reviewer_request()
    
    # 直接测试vLLM API
    test_direct_vllm_api()
    
    print("\n🎉 测试完成！") 