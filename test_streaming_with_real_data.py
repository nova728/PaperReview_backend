#!/usr/bin/env python3
"""
使用真实论文数据测试流式API的完整测试脚本
"""

import requests
import json
import time
import os
import sys
from pathlib import Path

def load_paper_example(filename):
    """加载指定的论文JSON文件"""
    paper_path = Path("static/papers") / filename
    if not paper_path.exists():
        raise FileNotFoundError(f"论文文件不存在: {paper_path}")
    
    with open(paper_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def test_streaming_api_with_paper(paper_json, paper_name, stream=True):
    """使用真实论文数据测试流式API"""
    
    # 构建请求数据
    test_data = {
        "paper_json": paper_json,
        "stream": stream,
        "temperature": 0.7,
        "max_tokens": 2048,
        "use_chunking": True
    }
    
    # API端点
    url = "http://localhost:8080/api/papers/peer-review"
    
    print(f"=== 测试论文: {paper_name} ({'流式' if stream else '非流式'}) ===")
    print(f"论文标题: {paper_json.get('title', 'N/A')}")
    print(f"作者数量: {len(paper_json.get('author', []))}")
    print(f"正文部分数: {len(paper_json.get('body', []))}")
    print(f"参考文献数: {len(paper_json.get('reference', []))}")
    print("=" * 60)
    
    try:
        start_time = time.time()
        
        if stream:
            # 流式请求
            response = requests.post(
                url,
                json=test_data,
                headers={'Content-Type': 'application/json'},
                stream=True,
                timeout=300
            )
            response.raise_for_status()
            
            print("📡 开始接收流式数据...\n")
            
            content_chunks = []
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        data_content = line_str[6:]
                        
                        try:
                            event_data = json.loads(data_content)
                            event_type = event_data.get('type', 'unknown')
                            
                            if event_type == 'start':
                                print(f"🟢 [开始] {event_data.get('message', '')}")
                                stats = event_data.get('stats', {})
                                print(f"   输入长度: {stats.get('input_length', 0):,}")
                                print(f"   分块处理: {stats.get('use_chunking', False)}")
                                print()
                                
                            elif event_type == 'content':
                                content = event_data.get('content', '')
                                content_chunks.append(content)
                                print(content, end='', flush=True)
                                
                            elif event_type == 'end':
                                end_time = time.time()
                                print(f"\n\n🟢 [完成] {event_data.get('message', '')}")
                                stats = event_data.get('stats', {})
                                print(f"   处理时间: {stats.get('processing_time', 0):.2f}秒")
                                print(f"   实际响应时间: {end_time - start_time:.2f}秒")
                                print(f"   输出长度: {stats.get('output_length', 0):,}")
                                print(f"   处理方法: {stats.get('processing_method', '')}")
                                
                                # 验证内容一致性
                                full_content = ''.join(content_chunks)
                                reported_length = stats.get('output_length', 0)
                                actual_length = len(full_content)
                                if abs(reported_length - actual_length) > 10:  # 允许小差异
                                    print(f"⚠️  长度不一致: 报告={reported_length}, 实际={actual_length}")
                                else:
                                    print(f"✅ 内容长度验证通过")
                                
                            elif event_type == 'error':
                                print(f"\n🔴 [错误] {event_data.get('error', '')}")
                                return False
                                
                        except json.JSONDecodeError:
                            continue
            
            return True
            
        else:
            # 非流式请求
            response = requests.post(
                url,
                json=test_data,
                headers={'Content-Type': 'application/json'},
                timeout=300
            )
            response.raise_for_status()
            
            end_time = time.time()
            result = response.json()
            
            print(f"🟢 非流式请求完成")
            print(f"响应时间: {end_time - start_time:.2f}秒")
            print(f"成功状态: {result.get('success', False)}")
            
            if result.get('stats'):
                stats = result['stats']
                print(f"输入长度: {stats.get('input_length', 0):,}")
                print(f"输出长度: {stats.get('output_length', 0):,}")
                print(f"处理方法: {stats.get('processing_method', '')}")
                print(f"处理时间: {stats.get('processing_time', 0):.2f}秒")
            
            if result.get('response'):
                response_text = result['response']
                print(f"\n生成的评审预览 (前500字符):")
                print("-" * 50)
                print(response_text[:500])
                if len(response_text) > 500:
                    print("...")
                print("-" * 50)
            
            return result.get('success', False)
        
    except requests.exceptions.RequestException as e:
        print(f"🔴 请求失败: {e}")
        return False
    except Exception as e:
        print(f"🔴 未知错误: {e}")
        return False

def main():
    """主测试函数"""
    print("🚀 使用真实论文数据测试流式API")
    print("=" * 60)
    
    # 检查服务是否运行
    try:
        health_response = requests.get("http://localhost:8080/api/papers/health", timeout=5)
        if health_response.status_code == 200:
            print("✅ 后端服务运行正常")
        else:
            print("⚠️  后端服务响应异常")
    except requests.exceptions.RequestException:
        print("❌ 无法连接到后端服务，请确保 app.py 正在运行")
        print("启动命令: cd Hammer_review_backend && python app.py")
        return
    
    # 获取可用的论文文件
    papers_dir = Path("static/papers")
    if not papers_dir.exists():
        print(f"❌ 论文目录不存在: {papers_dir}")
        return
    
    json_files = list(papers_dir.glob("*.json"))
    if not json_files:
        print(f"❌ 在 {papers_dir} 中未找到JSON文件")
        return
    
    # 选择几个不同大小的文件进行测试
    test_files = []
    json_files_with_size = [(f, f.stat().st_size) for f in json_files]
    json_files_with_size.sort(key=lambda x: x[1])
    
    # 选择小、中、大三个文件
    if len(json_files_with_size) >= 3:
        test_files = [
            json_files_with_size[0][0],      # 最小的
            json_files_with_size[len(json_files_with_size)//2][0],  # 中等的
            json_files_with_size[-1][0]      # 最大的
        ]
    else:
        test_files = [f[0] for f in json_files_with_size[:3]]
    
    print(f"📋 将测试 {len(test_files)} 个论文文件:")
    for i, file_path in enumerate(test_files, 1):
        size_kb = file_path.stat().st_size / 1024
        print(f"  {i}. {file_path.name} ({size_kb:.1f} KB)")
    
    print()
    
    # 执行测试
    results = []
    
    for i, paper_file in enumerate(test_files, 1):
        print(f"\n{'='*80}")
        print(f"测试 {i}/{len(test_files)}: {paper_file.name}")
        print(f"{'='*80}")
        
        try:
            # 加载论文数据
            paper_json = load_paper_example(paper_file.name)
            
            # 测试流式API
            stream_success = test_streaming_api_with_paper(paper_json, paper_file.name, stream=True)
            
            print(f"\n{'-'*40}")
            
            # 测试非流式API作为对比
            non_stream_success = test_streaming_api_with_paper(paper_json, paper_file.name, stream=False)
            
            results.append({
                'file': paper_file.name,
                'stream_success': stream_success,
                'non_stream_success': non_stream_success,
                'size_kb': paper_file.stat().st_size / 1024
            })
            
        except Exception as e:
            print(f"🔴 测试失败: {e}")
            results.append({
                'file': paper_file.name,
                'stream_success': False,
                'non_stream_success': False,
                'size_kb': paper_file.stat().st_size / 1024
            })
    
    # 汇总报告
    print(f"\n{'='*80}")
    print("📊 测试汇总报告")
    print(f"{'='*80}")
    
    total_tests = len(results)
    stream_successes = sum(1 for r in results if r['stream_success'])
    non_stream_successes = sum(1 for r in results if r['non_stream_success'])
    
    print(f"测试文件数: {total_tests}")
    print(f"流式API成功: {stream_successes}/{total_tests}")
    print(f"非流式API成功: {non_stream_successes}/{total_tests}")
    
    print(f"\n详细结果:")
    print(f"{'文件名':<30} {'大小(KB)':<10} {'流式':<6} {'非流式':<6}")
    print("-" * 55)
    
    for result in results:
        stream_status = "✅" if result['stream_success'] else "❌"
        non_stream_status = "✅" if result['non_stream_success'] else "❌"
        print(f"{result['file']:<30} {result['size_kb']:<10.1f} {stream_status:<6} {non_stream_status:<6}")
    
    if stream_successes == total_tests and non_stream_successes == total_tests:
        print(f"\n🎉 所有测试通过！流式API工作正常。")
    else:
        print(f"\n⚠️  部分测试失败，请检查日志。")

if __name__ == "__main__":
    main() 