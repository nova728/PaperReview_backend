#!/usr/bin/env python3
"""
PDF结构文件性能测试脚本 - 同时显示字符数和Token数
"""

import json
import time
import requests
import statistics
from pathlib import Path
from typing import Dict, Any, List
from dataclasses import dataclass
import sys
import argparse
import re

@dataclass
class TestResult:
    """测试结果数据类"""
    file_name: str
    file_size: int
    input_length: int
    output_length: int
    input_tokens: int
    output_tokens: int
    processing_time: float
    processing_method: str
    success: bool
    error_message: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_name": self.file_name,
            "file_size": self.file_size,
            "input_length": self.input_length,
            "output_length": self.output_length,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "processing_time": self.processing_time,
            "processing_method": self.processing_method,
            "success": self.success,
            "error_message": self.error_message
        }

class TokenCounter:
    """Token计数器"""
    
    @staticmethod
    def estimate_tokens(text: str) -> int:
        """估算token数量"""
        if not text:
            return 0
        
        # 统计中文字符数
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        
        # 统计英文单词数
        english_words = len(re.findall(r'[a-zA-Z]+', text))
        
        # 统计数字和符号
        numbers_symbols = len(re.findall(r'[0-9\.\,\!\?\;\:\(\)\[\]\{\}\-\+\=\*\/\\\@\#\$\%\^\&]', text))
        
        # 统计空格和换行
        whitespace = len(re.findall(r'\s', text))
        
        # Token估算规则:
        # - 中文字符: 1.5 字符 = 1 token
        # - 英文单词: 1 单词 = 1 token  
        # - 数字符号: 2 字符 = 1 token
        # - 空格换行: 4 字符 = 1 token
        
        estimated_tokens = (
            chinese_chars / 1.5 +
            english_words +
            numbers_symbols / 2 +
            whitespace / 4
        )
        
        return int(estimated_tokens)

class PerformanceTester:
    """性能测试器"""
    
    def __init__(self, backend_url: str = "http://localhost:8080", max_tokens: int = 8192):
        self.backend_url = backend_url.rstrip('/')
        self.max_tokens = max_tokens
        self.results_dir = Path("test_results")
        self.results_dir.mkdir(exist_ok=True)

        self.token_counter = TokenCounter()
        
        # 测试文件列表 - 使用具体的PDF结构文件
        self.test_files = [
            "static/papers/Agent_laboratory.txt",
            "static/papers/DeepSeekMath.txt", 
            "static/papers/HuggingGPT.txt",
            "static/papers/IntellAgent.txt",
            "static/papers/Pasa.txt",
            "static/papers/pdfStruct.txt",
            "static/papers/The AI Scientist.txt"
        ]
    
    def run_comprehensive_test(self, num_rounds: int = 3) -> Dict[str, Any]:
        """运行综合性能测试"""
        print(f"开始性能测试 (轮数: {num_rounds}, max_tokens: {self.max_tokens})")
        
        # 检查后端服务
        if not self._check_backend_health():
            print("后端服务不可用")
            return {}
        
        # 验证测试文件
        available_files = self._get_available_test_files()
        if not available_files:
            print("没有找到测试文件")
            return {}
        
        print(f"找到 {len(available_files)} 个测试文件")
        for file_info in available_files:
            print(f"  - {file_info['name']} ({file_info['size_kb']:.1f} KB, {file_info['content_length']} 字符, ~{file_info['estimated_tokens']} tokens)")
        
        all_results = []
        
        # 对每个文件进行多轮测试
        for round_num in range(1, num_rounds + 1):
            print(f"\n第 {round_num}/{num_rounds} 轮测试")
            
            for file_info in available_files:
                print(f"  测试文件: {file_info['name']}")
                result = self._test_single_file(file_info, round_num)
                all_results.append(result)
                
                # 显示结果
                if result.success:
                    print(f"    成功 - 用时: {result.processing_time:.2f}s")
                    print(f"    输入: {result.input_length} 字符 ({result.input_tokens} tokens)")
                    print(f"    输出: {result.output_length} 字符 ({result.output_tokens} tokens)")
                else:
                    print(f"    失败 - {result.error_message}")
                
                # 避免过于频繁的请求
                time.sleep(1)
        
        # 分析结果
        analysis = self._analyze_results(all_results)
        
        # 保存结果
        self._save_results(all_results, analysis)
        
        # 显示摘要
        self._print_summary(analysis)
        
        return analysis
    
    def _check_backend_health(self) -> bool:
        """检查后端服务健康状态"""
        try:
            response = requests.get(f"{self.backend_url}/api/papers/health", timeout=10)
            return response.status_code == 200
        except Exception as e:
            print(f"后端健康检查失败: {e}")
            return False
    
    def _get_available_test_files(self) -> List[Dict[str, Any]]:
        """获取可用的测试文件列表"""
        available_files = []
        
        for file_path in self.test_files:
            full_path = Path(file_path)
            if full_path.exists():
                # 读取文件内容来估算token数
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                file_size = full_path.stat().st_size
                estimated_tokens = self.token_counter.estimate_tokens(content)
                
                available_files.append({
                    "name": full_path.stem,
                    "file_path": str(full_path),
                    "size_bytes": file_size,
                    "size_kb": file_size / 1024,
                    "content_length": len(content),
                    "estimated_tokens": estimated_tokens,
                    "content": content
                })
            else:
                print(f"警告: 文件不存在 {file_path}")
        
        # 按文件大小排序
        available_files.sort(key=lambda x: x['size_bytes'])
        
        return available_files
    
    def _test_single_file(self, file_info: Dict[str, Any], round_num: int) -> TestResult:
        """测试单个文件"""
        try:
            content = file_info['content']
            
            # 计算输入长度和tokens
            input_length = len(content)
            input_tokens = self.token_counter.estimate_tokens(content)
            
            # 尝试解析为JSON
            try:
                paper_json = json.loads(content)
            except json.JSONDecodeError:
                # 如果不是JSON格式，创建一个简单的结构
                paper_json = {
                    "title": f"Document from {file_info['name']}",
                    "content": content,
                    "body": [{"section": {"name": "Content"}, "p": [{"text": content}]}]
                }
            
            # 按照 test_request_json.json 的格式构建请求，使用更大的 max_tokens
            request_data = {
                "paper_json": paper_json,
                "temperature": 0.7,
                "max_tokens": self.max_tokens,
                "use_chunking": True
            }
            
            # 发送请求到 /api/papers/peer-review 端点
            start_time = time.time()
            response = requests.post(
                f"{self.backend_url}/api/papers/peer-review",
                json=request_data,
                headers={'Content-Type': 'application/json'},
                timeout=600
            )
            end_time = time.time()
            
            processing_time = end_time - start_time
            
            if response.status_code == 200:
                result_data = response.json()
                
                # 检查响应格式
                if result_data.get('success', False):
                    stats = result_data.get('stats', {})
                    response_text = result_data.get('response', '')
                    
                    # 计算输出长度和tokens
                    output_length = len(response_text)
                    output_tokens = self.token_counter.estimate_tokens(response_text)
                    
                    return TestResult(
                        file_name=f"{file_info['name']}_r{round_num}",
                        file_size=file_info['size_bytes'],
                        input_length=input_length,
                        output_length=output_length,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        processing_time=processing_time,
                        processing_method=stats.get('processing_method', 'unknown'),
                        success=True
                    )
                else:
                    # 后端返回失败响应
                    error_msg = result_data.get('error', 'Unknown error')
                    return TestResult(
                        file_name=f"{file_info['name']}_r{round_num}",
                        file_size=file_info['size_bytes'],
                        input_length=input_length,
                        output_length=0,
                        input_tokens=input_tokens,
                        output_tokens=0,
                        processing_time=processing_time,
                        processing_method="backend_error",
                        success=False,
                        error_message=f"Backend error: {error_msg}"
                    )
            else:
                return TestResult(
                    file_name=f"{file_info['name']}_r{round_num}",
                    file_size=file_info['size_bytes'],
                    input_length=input_length,
                    output_length=0,
                    input_tokens=input_tokens,
                    output_tokens=0,
                    processing_time=processing_time,
                    processing_method="http_error",
                    success=False,
                    error_message=f"HTTP {response.status_code}: {response.text[:200]}"
                )
        
        except Exception as e:
            return TestResult(
                file_name=f"{file_info['name']}_r{round_num}",
                file_size=file_info.get('size_bytes', 0),
                input_length=0,
                output_length=0,
                input_tokens=0,
                output_tokens=0,
                processing_time=0,
                processing_method="exception",
                success=False,
                error_message=str(e)
            )
    
    def _analyze_results(self, results: List[TestResult]) -> Dict[str, Any]:
        """分析测试结果"""
        successful_results = [r for r in results if r.success]
        failed_results = [r for r in results if not r.success]
        
        if not successful_results:
            return {
                "total_tests": len(results),
                "successful_tests": 0,
                "failed_tests": len(failed_results),
                "success_rate": 0.0,
                "max_tokens_used": self.max_tokens
            }
        
        # 按文件大小分组
        size_groups = {}
        for result in successful_results:
            size_range = self._get_size_range(result.file_size)
            if size_range not in size_groups:
                size_groups[size_range] = []
            size_groups[size_range].append(result)
        
        # 按文件名分组
        file_groups = {}
        for result in successful_results:
            file_name = result.file_name.split('_r')[0]  # 移除轮次后缀
            if file_name not in file_groups:
                file_groups[file_name] = []
            file_groups[file_name].append(result)
        
        # 按处理方法分组
        method_groups = {}
        for result in successful_results:
            method = result.processing_method
            if method not in method_groups:
                method_groups[method] = []
            method_groups[method].append(result)
        
        # 计算统计信息
        processing_times = [r.processing_time for r in successful_results]
        input_lengths = [r.input_length for r in successful_results]
        output_lengths = [r.output_length for r in successful_results]
        input_tokens = [r.input_tokens for r in successful_results]
        output_tokens = [r.output_tokens for r in successful_results]
        
        # 计算输出与输入的比率
        char_output_input_ratios = []
        token_output_input_ratios = []
        for result in successful_results:
            if result.input_length > 0:
                char_ratio = result.output_length / result.input_length
                char_output_input_ratios.append(char_ratio)
            if result.input_tokens > 0:
                token_ratio = result.output_tokens / result.input_tokens
                token_output_input_ratios.append(token_ratio)
        
        # 计算token利用率
        token_utilization = [
            (r.output_tokens / self.max_tokens) * 100
            for r in successful_results
        ]
        
        analysis = {
            "total_tests": len(results),
            "successful_tests": len(successful_results),
            "failed_tests": len(failed_results),
            "success_rate": len(successful_results) / len(results) * 100,
            "max_tokens_used": self.max_tokens,
            
            "processing_time_stats": {
                "mean": statistics.mean(processing_times),
                "median": statistics.median(processing_times),
                "min": min(processing_times),
                "max": max(processing_times),
                "std_dev": statistics.stdev(processing_times) if len(processing_times) > 1 else 0
            },
            
            "input_length_stats": {
                "mean": statistics.mean(input_lengths),
                "median": statistics.median(input_lengths),
                "min": min(input_lengths),
                "max": max(input_lengths),
                "std_dev": statistics.stdev(input_lengths) if len(input_lengths) > 1 else 0
            },
            
            "output_length_stats": {
                "mean": statistics.mean(output_lengths),
                "median": statistics.median(output_lengths),
                "min": min(output_lengths),
                "max": max(output_lengths),
                "std_dev": statistics.stdev(output_lengths) if len(output_lengths) > 1 else 0
            },
            
            "input_token_stats": {
                "mean": statistics.mean(input_tokens),
                "median": statistics.median(input_tokens),
                "min": min(input_tokens),
                "max": max(input_tokens),
                "std_dev": statistics.stdev(input_tokens) if len(input_tokens) > 1 else 0
            },
            
            "output_token_stats": {
                "mean": statistics.mean(output_tokens),
                "median": statistics.median(output_tokens),
                "min": min(output_tokens),
                "max": max(output_tokens),
                "std_dev": statistics.stdev(output_tokens) if len(output_tokens) > 1 else 0
            },
            
            "token_utilization_stats": {
                "mean": statistics.mean(token_utilization),
                "median": statistics.median(token_utilization),
                "min": min(token_utilization),
                "max": max(token_utilization),
                "std_dev": statistics.stdev(token_utilization) if len(token_utilization) > 1 else 0
            },
            
            "char_output_input_ratio_stats": {
                "mean": statistics.mean(char_output_input_ratios) if char_output_input_ratios else 0,
                "median": statistics.median(char_output_input_ratios) if char_output_input_ratios else 0,
                "min": min(char_output_input_ratios) if char_output_input_ratios else 0,
                "max": max(char_output_input_ratios) if char_output_input_ratios else 0,
                "std_dev": statistics.stdev(char_output_input_ratios) if len(char_output_input_ratios) > 1 else 0
            },
            
            "token_output_input_ratio_stats": {
                "mean": statistics.mean(token_output_input_ratios) if token_output_input_ratios else 0,
                "median": statistics.median(token_output_input_ratios) if token_output_input_ratios else 0,
                "min": min(token_output_input_ratios) if token_output_input_ratios else 0,
                "max": max(token_output_input_ratios) if token_output_input_ratios else 0,
                "std_dev": statistics.stdev(token_output_input_ratios) if len(token_output_input_ratios) > 1 else 0
            },
            
            "size_group_performance": {},
            "file_performance": {},
            "method_performance": {},
            
            "failed_tests_summary": [
                {
                    "file_name": r.file_name,
                    "error_message": r.error_message
                } for r in failed_results[:10]  # 只显示前10个失败案例
            ]
        }
        
        # 按大小分组的性能统计
        for size_range, group_results in size_groups.items():
            times = [r.processing_time for r in group_results]
            char_outputs = [r.output_length for r in group_results]
            token_outputs = [r.output_tokens for r in group_results]
            
            analysis["size_group_performance"][size_range] = {
                "count": len(group_results),
                "avg_processing_time": statistics.mean(times),
                "avg_input_length": statistics.mean([r.input_length for r in group_results]),
                "avg_output_length": statistics.mean(char_outputs),
                "avg_input_tokens": statistics.mean([r.input_tokens for r in group_results]),
                "avg_output_tokens": statistics.mean(token_outputs),
                "std_output_length": statistics.stdev(char_outputs) if len(char_outputs) > 1 else 0,
                "std_output_tokens": statistics.stdev(token_outputs) if len(token_outputs) > 1 else 0
            }
        
        # 按文件分组的性能统计
        for file_name, group_results in file_groups.items():
            times = [r.processing_time for r in group_results]
            char_outputs = [r.output_length for r in group_results]
            token_outputs = [r.output_tokens for r in group_results]
            
            analysis["file_performance"][file_name] = {
                "count": len(group_results),
                "avg_processing_time": statistics.mean(times),
                "std_processing_time": statistics.stdev(times) if len(times) > 1 else 0,
                "avg_input_length": statistics.mean([r.input_length for r in group_results]),
                "avg_output_length": statistics.mean(char_outputs),
                "avg_input_tokens": statistics.mean([r.input_tokens for r in group_results]),
                "avg_output_tokens": statistics.mean(token_outputs),
                "std_output_length": statistics.stdev(char_outputs) if len(char_outputs) > 1 else 0,
                "std_output_tokens": statistics.stdev(token_outputs) if len(token_outputs) > 1 else 0,
                "file_size_kb": group_results[0].file_size / 1024
            }
        
        # 按处理方法分组的性能统计
        for method, group_results in method_groups.items():
            times = [r.processing_time for r in group_results]
            char_outputs = [r.output_length for r in group_results]
            token_outputs = [r.output_tokens for r in group_results]
            
            analysis["method_performance"][method] = {
                "count": len(group_results),
                "avg_processing_time": statistics.mean(times),
                "avg_input_length": statistics.mean([r.input_length for r in group_results]),
                "avg_output_length": statistics.mean(char_outputs),
                "avg_input_tokens": statistics.mean([r.input_tokens for r in group_results]),
                "avg_output_tokens": statistics.mean(token_outputs),
                "std_output_length": statistics.stdev(char_outputs) if len(char_outputs) > 1 else 0,
                "std_output_tokens": statistics.stdev(token_outputs) if len(token_outputs) > 1 else 0
            }
        
        return analysis
    
    def _get_size_range(self, file_size: int) -> str:
        """获取文件大小范围"""
        size_kb = file_size / 1024
        if size_kb < 50:
            return "< 50KB"
        elif size_kb < 100:
            return "50-100KB"
        elif size_kb < 200:
            return "100-200KB"
        elif size_kb < 500:
            return "200-500KB"
        elif size_kb < 1000:
            return "500KB-1MB"
        else:
            return "> 1MB"
    
    def _save_results(self, results: List[TestResult], analysis: Dict[str, Any]):
        """保存测试结果"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        
        # 保存详细结果
        detailed_results = {
            "timestamp": timestamp,
            "test_files": self.test_files,
            "backend_url": self.backend_url,
            "max_tokens": self.max_tokens,
            "results": [r.to_dict() for r in results],
            "analysis": analysis
        }
        
        results_file = self.results_dir / f"performance_test_{timestamp}.json"
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(detailed_results, f, ensure_ascii=False, indent=2)
        
        print(f"\n详细结果已保存: {results_file}")
        
        # 保存CSV格式的结果摘要
        csv_file = self.results_dir / f"performance_summary_{timestamp}.csv"
        with open(csv_file, 'w', encoding='utf-8') as f:
            f.write("file_name,file_size_kb,input_length,output_length,input_tokens,output_tokens,token_utilization,char_output_input_ratio,token_output_input_ratio,processing_time,processing_method,success\n")
            for result in results:
                if result.success:
                    token_utilization = (result.output_tokens / self.max_tokens) * 100
                    char_ratio = result.output_length / result.input_length if result.input_length > 0 else 0
                    token_ratio = result.output_tokens / result.input_tokens if result.input_tokens > 0 else 0
                    f.write(f"{result.file_name},{result.file_size/1024:.1f},{result.input_length},"
                           f"{result.output_length},{result.input_tokens},{result.output_tokens},"
                           f"{token_utilization:.1f}%,{char_ratio:.3f},{token_ratio:.3f},"
                           f"{result.processing_time:.2f},{result.processing_method},{result.success}\n")
                else:
                    f.write(f"{result.file_name},{result.file_size/1024:.1f},{result.input_length},"
                           f"0,{result.input_tokens},0,0%,0,0,"
                           f"{result.processing_time:.2f},{result.processing_method},{result.success}\n")
        
        print(f"CSV摘要已保存: {csv_file}")
    
    def _print_summary(self, analysis: Dict[str, Any]):
        """打印测试摘要"""
        print("\n" + "="*60)
        print("性能测试摘要 (字符数 + Token统计)")
        print("="*60)
        
        print(f"总测试数: {analysis['total_tests']}")
        print(f"成功测试: {analysis['successful_tests']}")
        print(f"失败测试: {analysis['failed_tests']}")
        print(f"成功率: {analysis['success_rate']:.1f}%")
        print(f"最大Token数: {analysis['max_tokens_used']}")
        
        if analysis['successful_tests'] > 0:
            time_stats = analysis['processing_time_stats']
            print(f"\n处理时间统计:")
            print(f"  平均: {time_stats['mean']:.2f}s")
            print(f"  中位数: {time_stats['median']:.2f}s")
            print(f"  最小值: {time_stats['min']:.2f}s")
            print(f"  最大值: {time_stats['max']:.2f}s")
            print(f"  标准差: {time_stats['std_dev']:.2f}s")
            
            input_len_stats = analysis['input_length_stats']
            print(f"\n输入字符数统计:")
            print(f"  平均: {input_len_stats['mean']:.0f} 字符")
            print(f"  中位数: {input_len_stats['median']:.0f} 字符")
            print(f"  最小值: {input_len_stats['min']:.0f} 字符")
            print(f"  最大值: {input_len_stats['max']:.0f} 字符")
            print(f"  标准差: {input_len_stats['std_dev']:.0f} 字符")
            
            output_len_stats = analysis['output_length_stats']
            print(f"\n输出字符数统计:")
            print(f"  平均: {output_len_stats['mean']:.0f} 字符")
            print(f"  中位数: {output_len_stats['median']:.0f} 字符")
            print(f"  最小值: {output_len_stats['min']:.0f} 字符")
            print(f"  最大值: {output_len_stats['max']:.0f} 字符")
            print(f"  标准差: {output_len_stats['std_dev']:.0f} 字符")
            
            input_token_stats = analysis['input_token_stats']
            print(f"\n输入Token统计:")
            print(f"  平均: {input_token_stats['mean']:.0f} tokens")
            print(f"  中位数: {input_token_stats['median']:.0f} tokens")
            print(f"  最小值: {input_token_stats['min']:.0f} tokens")
            print(f"  最大值: {input_token_stats['max']:.0f} tokens")
            print(f"  标准差: {input_token_stats['std_dev']:.0f} tokens")
            
            output_token_stats = analysis['output_token_stats']
            print(f"\n输出Token统计:")
            print(f"  平均: {output_token_stats['mean']:.0f} tokens")
            print(f"  中位数: {output_token_stats['median']:.0f} tokens")
            print(f"  最小值: {output_token_stats['min']:.0f} tokens")
            print(f"  最大值: {output_token_stats['max']:.0f} tokens")
            print(f"  标准差: {output_token_stats['std_dev']:.0f} tokens")
            
            util_stats = analysis['token_utilization_stats']
            print(f"\nToken利用率统计:")
            print(f"  平均: {util_stats['mean']:.1f}%")
            print(f"  中位数: {util_stats['median']:.1f}%")
            print(f"  最小值: {util_stats['min']:.1f}%")
            print(f"  最大值: {util_stats['max']:.1f}%")
            
            char_ratio_stats = analysis['char_output_input_ratio_stats']
            print(f"\n输出/输入字符比率统计:")
            print(f"  平均: {char_ratio_stats['mean']:.3f}")
            print(f"  中位数: {char_ratio_stats['median']:.3f}")
            print(f"  最小值: {char_ratio_stats['min']:.3f}")
            print(f"  最大值: {char_ratio_stats['max']:.3f}")
            
            token_ratio_stats = analysis['token_output_input_ratio_stats']
            print(f"\n输出/输入Token比率统计:")
            print(f"  平均: {token_ratio_stats['mean']:.3f}")
            print(f"  中位数: {token_ratio_stats['median']:.3f}")
            print(f"  最小值: {token_ratio_stats['min']:.3f}")
            print(f"  最大值: {token_ratio_stats['max']:.3f}")
            
            print(f"\n文件大小性能:")
            for size_range, stats in analysis['size_group_performance'].items():
                print(f"  {size_range}: {stats['count']} 测试, "
                      f"平均用时 {stats['avg_processing_time']:.2f}s")
                print(f"    平均输出: {stats['avg_output_length']:.0f} 字符 ({stats['avg_output_tokens']:.0f} tokens)")
            
            print(f"\n处理方法性能:")
            for method, stats in analysis['method_performance'].items():
                print(f"  {method}: {stats['count']} 测试, "
                      f"平均用时 {stats['avg_processing_time']:.2f}s")
                print(f"    平均输出: {stats['avg_output_length']:.0f} 字符 ({stats['avg_output_tokens']:.0f} tokens)")
            
            print(f"\n单文件性能:")
            for file_name, stats in analysis['file_performance'].items():
                print(f"  {file_name} ({stats['file_size_kb']:.1f}KB): {stats['count']} 测试")
                print(f"    平均用时: {stats['avg_processing_time']:.2f}s (±{stats['std_processing_time']:.2f}s)")
                print(f"    平均输出: {stats['avg_output_length']:.0f} 字符 (±{stats['std_output_length']:.0f})")
                print(f"    平均输出: {stats['avg_output_tokens']:.0f} tokens (±{stats['std_output_tokens']:.0f})")
        
        if analysis['failed_tests'] > 0:
            print(f"\n失败测试样例:")
            for failed in analysis['failed_tests_summary'][:5]:
                print(f"  {failed['file_name']}: {failed['error_message'][:80]}")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="PDF结构文件性能测试 (字符数 + Token统计)")
    parser.add_argument("--backend-url", default="http://localhost:8080", 
                       help="后端服务URL (默认: http://localhost:8080)")
    parser.add_argument("--rounds", type=int, default=3, 
                       help="测试轮数 (默认: 3)")
    parser.add_argument("--max-tokens", type=int, default=8192,
                       help="最大生成Token数 (默认: 8192)")
    
    args = parser.parse_args()
    
    # 运行性能测试
    tester = PerformanceTester(args.backend_url, args.max_tokens)
    tester.run_comprehensive_test(args.rounds)

if __name__ == "__main__":
    main()