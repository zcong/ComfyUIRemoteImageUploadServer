#!/usr/bin/env python3
"""
ComfyUI远程图片上传服务端
接收来自ComfyUI节点的图片上传请求
"""

import os
import json
import logging
import random
import string
from datetime import datetime
from flask import Flask, request, jsonify, abort
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('upload_server.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 默认配置
DEFAULT_CONFIG = {
    "port": 65360,
    "api_key": "default_secret_key_change_me",
    "upload_dir": "images",
    "max_file_size": 50 * 1024 * 1024  # 50MB
}

# 加载配置
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")
config = DEFAULT_CONFIG.copy()

if os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            user_config = json.load(f)
            config.update(user_config)
            logger.info(f"已加载配置文件: {CONFIG_FILE}")
    except Exception as e:
        logger.warning(f"加载配置文件失败，使用默认配置: {e}")
else:
    logger.info(f"配置文件不存在，使用默认配置。配置文件路径: {CONFIG_FILE}")

# 设置上传目录
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "..", config["upload_dir"])
UPLOAD_FOLDER = os.path.abspath(UPLOAD_FOLDER)

# 确保上传目录存在
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
    logger.info(f"创建上传目录: {UPLOAD_FOLDER}")
else:
    logger.info(f"使用上传目录: {UPLOAD_FOLDER}")

# 允许的文件扩展名
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'}

# 设置最大文件大小
app.config['MAX_CONTENT_LENGTH'] = config.get("max_file_size", 50 * 1024 * 1024)


def allowed_file(filename):
    """检查文件扩展名是否允许"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def generate_random_string(length=8):
    """生成随机字符串"""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))


def generate_filename(original_filename):
    """
    生成新文件名：comfyui_ + 随机数 + 原始扩展名
    
    Args:
        original_filename: 原始文件名
    
    Returns:
        新文件名
    """
    # 获取文件扩展名
    if '.' in original_filename:
        ext = original_filename.rsplit('.', 1)[1].lower()
    else:
        ext = 'png'  # 默认使用png
    
    # 生成随机数（8位）
    random_str = generate_random_string(8)
    
    # 组合文件名
    new_filename = f"comfyui_{random_str}.{ext}"
    
    return new_filename


@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(e):
    """处理文件过大错误"""
    logger.warning(f"文件过大: {request.remote_addr}")
    return jsonify({
        "error": "文件大小超过限制",
        "max_size": f"{config.get('max_file_size', 50 * 1024 * 1024) / (1024 * 1024):.0f}MB"
    }), 413


@app.route('/upload', methods=['POST'])
def upload_file():
    """
    处理文件上传请求
    
    验证X-API-KEY header，接收文件并保存到images目录
    """
    client_ip = request.remote_addr
    logger.info(f"收到上传请求，来源IP: {client_ip}")
    
    # 验证API密钥
    api_key = request.headers.get("X-API-KEY", "")
    if not api_key:
        logger.warning(f"请求缺少API密钥，来源IP: {client_ip}")
        return jsonify({"error": "缺少API密钥"}), 401
    
    if api_key != config["api_key"]:
        logger.warning(f"API密钥验证失败，来源IP: {client_ip}")
        return jsonify({"error": "API密钥无效"}), 401
    
    logger.info(f"API密钥验证通过，来源IP: {client_ip}")
    
    # 检查文件是否存在
    if 'file' not in request.files:
        logger.warning(f"请求中未包含文件，来源IP: {client_ip}")
        return jsonify({"error": "请求中未包含文件"}), 400
    
    file = request.files['file']
    
    # 检查文件名
    if file.filename == '':
        logger.warning(f"文件名为空，来源IP: {client_ip}")
        return jsonify({"error": "文件名为空"}), 400
    
    # 检查文件类型
    if not allowed_file(file.filename):
        logger.warning(f"不允许的文件类型: {file.filename}，来源IP: {client_ip}")
        return jsonify({
            "error": "不允许的文件类型",
            "allowed_types": list(ALLOWED_EXTENSIONS)
        }), 400
    
    # 生成新文件名
    original_filename = secure_filename(file.filename)
    new_filename = generate_filename(original_filename)
    save_path = os.path.join(UPLOAD_FOLDER, new_filename)
    
    # 确保文件名唯一（如果文件已存在，添加时间戳）
    if os.path.exists(save_path):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name, ext = os.path.splitext(new_filename)
        new_filename = f"{name}_{timestamp}{ext}"
        save_path = os.path.join(UPLOAD_FOLDER, new_filename)
    
    try:
        # 保存文件
        file.save(save_path)
        file_size = os.path.getsize(save_path)
        logger.info(f"文件上传成功: {new_filename} ({file_size} bytes)，来源IP: {client_ip}")
        
        return jsonify({
            "message": "文件上传成功",
            "filename": new_filename,
            "size": file_size,
            "path": save_path
        }), 200
        
    except Exception as e:
        logger.error(f"保存文件失败: {str(e)}，来源IP: {client_ip}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "error": "保存文件失败",
            "details": str(e)
        }), 500


@app.route('/health', methods=['GET'])
def health_check():
    """健康检查端点"""
    return jsonify({
        "status": "ok",
        "upload_dir": UPLOAD_FOLDER,
        "config_loaded": os.path.exists(CONFIG_FILE)
    }), 200


@app.route('/', methods=['GET'])
def index():
    """根路径，返回服务信息"""
    return jsonify({
        "service": "ComfyUI Remote Image Upload Server",
        "version": "1.0.0",
        "endpoints": {
            "upload": "/upload (POST)",
            "health": "/health (GET)"
        }
    }), 200


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="ComfyUI远程图片上传服务端")
    parser.add_argument(
        '--port',
        type=int,
        default=config["port"],
        help=f'服务端口 (默认: {config["port"]})'
    )
    parser.add_argument(
        '--host',
        type=str,
        default='0.0.0.0',
        help='监听地址 (默认: 0.0.0.0)'
    )
    parser.add_argument(
        '--api-key',
        type=str,
        default=None,
        help='API密钥（会覆盖配置文件中的设置）'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='启用调试模式'
    )
    
    args = parser.parse_args()
    
    # 如果通过命令行指定了API密钥，覆盖配置
    if args.api_key:
        config["api_key"] = args.api_key
        logger.info("使用命令行指定的API密钥")
    
    logger.info("=" * 50)
    logger.info("ComfyUI远程图片上传服务端启动")
    logger.info(f"监听地址: {args.host}:{args.port}")
    logger.info(f"上传目录: {UPLOAD_FOLDER}")
    logger.info(f"API密钥: {'*' * len(config['api_key'])} (已隐藏)")
    logger.info(f"配置文件: {CONFIG_FILE}")
    logger.info("=" * 50)
    
    app.run(
        host=args.host,
        port=args.port,
        debug=args.debug
    )

