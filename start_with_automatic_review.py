#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
启动脚本 - 包含Automatic_Review集成功能的Hammer_review_backend
"""

import sys
import subprocess
import time
import requests

def start_server():
    """启动服务器"""
    print("启动Hammer_review_backend服务器...")
    
    try:
        # 启动服务器
        process = subprocess.Popen([
            sys.executable, "run.py"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # 等待服务器启动
        print("等待服务器启动...")
        time.sleep(3)
        
        # 检查服务器是否启动成功
        try:
            response = requests.get("http://localhost:8080/api/papers/health", timeout=5)
            if response.status_code == 200:
                print("服务器启动成功!")
                print("API地址: http://localhost:8080")
                print("健康检查: http://localhost:8080/api/papers/health")
                return process
            else:
                print(f"服务器响应异常: {response.status_code}")
                process.terminate()
                return None
        except requests.exceptions.RequestException:
            print("无法连接到服务器")
            process.terminate()
            return None
            
    except Exception as e:
        print(f"启动服务器失败: {str(e)}")
        return None

def show_usage_examples():
    """显示使用示例"""
    print("\n使用示例:")
    print("=" * 50)
    
    print("1. 基本评审:")
    print("   curl -X POST http://localhost:8080/api/papers/peer-review \\")
    print("     -H 'Content-Type: application/json' \\")
    print("     -d @test_request_json.json")
    
    print("\n2. Automatic_Review评审:")
    print("   curl -X POST http://localhost:8080/api/papers/automatic-review \\")
    print("     -H 'Content-Type: application/json' \\")
    print("     -d '{")
    print('       "paper_json": {"title": "Test", "abstract": [["Test"]], "body": [], "reference": []}')
    print("     }'")
    
    print("\n3. 方面分类:")
    print("   curl -X POST http://localhost:8080/api/papers/review-aspects \\")
    print("     -H 'Content-Type: application/json' \\")
    print('     -d \'{"review_text": "This paper presents a novel approach..."}\'')

def main():
    """主函数"""
    print("Hammer_review_backend with Automatic_Review Integration")
    print("=" * 60)
    
    # 询问用户操作
    while True:
        print("\n请选择操作:")
        print("1. 启动服务器")
        print("2. 显示使用示例")
        print("3. 退出")
        
        choice = input("\n请输入选择 (1-3): ").strip()
        
        if choice == "1":
            process = start_server()
            if process:
                print("\n服务器正在运行...")
                print("按 Ctrl+C 停止服务器")
                try:
                    process.wait()
                except KeyboardInterrupt:
                    print("\n正在停止服务器...")
                    process.terminate()
                    process.wait()
                    print("服务器已停止")
        
        elif choice == "2":
            show_usage_examples()
        
        elif choice == "3":
            print("再见!")
            break
        
        else:
            print("无效选择，请重新输入")

if __name__ == "__main__":
    main() 