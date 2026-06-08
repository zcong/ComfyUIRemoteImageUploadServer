#!/usr/bin/env python3
"""
ComfyUI远程图片上传服务端
接收来自ComfyUI节点的图片上传请求
"""
import time
import os
import json
import logging
from datetime import datetime
from flask import Flask, request, jsonify, abort, send_from_directory, render_template, redirect, session
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
from remote_workflow_runner import create_remote_runner_routes

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
    "session_secret": "",
    "upload_dir": "images",
    "max_file_size": 1024 * 1024 * 1024  # 1GB
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
ALLOWED_VIDEO_EXTENSIONS = {
    "mp4", "mov", "mkv", "webm", "avi"
}
VIDEO_MIME_TYPES = {
    "mp4": "video/mp4",
    "mov": "video/quicktime",
    "mkv": "video/x-matroska",
    "webm": "video/webm",
    "avi": "video/x-msvideo",
}
PAGE_AUTH_SESSION_KEY = "page_access_granted"
# 设置最大文件大小
app.config['MAX_CONTENT_LENGTH'] = config.get("max_file_size", 50 * 1024 * 1024)
app.secret_key = config.get("session_secret") or config["api_key"]
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


def has_allowed_extension(filename, allowed_extensions):
    """检查文件扩展名是否允许。"""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_extensions


def allowed_file(filename):
    """检查图片扩展名是否允许。"""
    return has_allowed_extension(filename, ALLOWED_EXTENSIONS)


def allowed_video(filename):
    """检查视频扩展名是否允许。"""
    return has_allowed_extension(filename, ALLOWED_VIDEO_EXTENSIONS)


def validate_api_key(api_key):
    """验证 API 密钥。"""
    return bool(api_key) and api_key == config["api_key"]


def has_page_access():
    """检查当前会话是否已通过页面访问鉴权。"""
    return bool(session.get(PAGE_AUTH_SESSION_KEY))


def mark_page_access_granted():
    """标记当前会话已通过页面访问鉴权。"""
    session[PAGE_AUTH_SESSION_KEY] = True


def get_request_api_key():
    """从表单、查询参数或请求头中提取 API 密钥。"""
    if request.method == "POST":
        form_key = str(request.form.get("key", "")).strip()
        if form_key:
            return form_key
    return (
        str(request.args.get("key", "")).strip()
        or str(request.headers.get("X-API-KEY", "")).strip()
    )


def render_auth_page(action_url, page_title, page_heading, description, error=None):
    """渲染通用鉴权页面。"""
    return render_template(
        "view_auth.html",
        action_url=action_url,
        page_title=page_title,
        page_heading=page_heading,
        description=description,
        error=error,
    )


def require_page_access(action_url, page_title, page_heading, description):
    """统一处理页面访问鉴权。"""
    if has_page_access():
        return None

    api_key = get_request_api_key()
    if not api_key:
        return render_auth_page(action_url, page_title, page_heading, description)

    if not validate_api_key(api_key):
        return render_auth_page(
            action_url,
            page_title,
            page_heading,
            description,
            error="API密钥无效，请重新输入",
        ), 401

    mark_page_access_granted()
    return redirect(action_url)


def has_runner_api_access():
    """检查 remote-runner API 是否具备访问权限。"""
    return has_page_access() or validate_api_key(get_request_api_key())


def require_api_key(client_ip, action_label):
    """统一处理 API 密钥校验。"""
    if has_page_access():
        return "session", None, None

    api_key = request.headers.get("X-API-KEY", "")
    if not api_key:
        logger.warning(f"{action_label}缺少 API 密钥，来源IP: {client_ip}")
        return None, jsonify({"error": "缺少API密钥"}), 401
    if not validate_api_key(api_key):
        logger.warning(f"{action_label} API 密钥无效，来源IP: {client_ip}")
        return None, jsonify({"error": "API密钥无效"}), 401
    return api_key, None, None


def get_media_config(media_type):
    """返回媒体类型对应的校验函数、URL 前缀和显示名称。"""
    media_map = {
        "image": {
            "label": "图片",
            "allowed": allowed_file,
            "url_prefix": "/images",
        },
        "video": {
            "label": "视频",
            "allowed": allowed_video,
            "url_prefix": "/videos",
        },
    }
    return media_map[media_type]


def resolve_media_path(filename, media_type):
    """校验文件名并返回对应媒体文件的绝对路径。"""
    safe_filename = secure_filename(filename)
    if safe_filename != filename:
        abort(400, "Invalid filename")

    media_config = get_media_config(media_type)
    if not media_config["allowed"](safe_filename):
        abort(400, "File type not allowed")

    file_path = os.path.join(UPLOAD_FOLDER, safe_filename)
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        abort(404, "File not found")

    return safe_filename, file_path


def generate_filename(original_filename):
    """
    生成数字时间戳命名的新文件名。
    
    Args:
        original_filename: 原始文件名
    
    Returns:
        新文件名
    """
    if '.' in original_filename:
        ext = original_filename.rsplit('.', 1)[1].lower()
    else:
        ext = 'png'

    timestamp = str(time.time_ns())
    return f"{timestamp}.{ext}"


def build_unique_save_path(filename):
    """为文件名生成不冲突的保存路径，并保持纯数字时间排序。"""
    name, ext = os.path.splitext(filename)
    try:
        candidate = int(name)
    except ValueError:
        candidate = time.time_ns()

    while True:
        filename = f"{candidate}{ext}"
        save_path = os.path.join(UPLOAD_FOLDER, filename)
        if not os.path.exists(save_path):
            return filename, save_path
        candidate += 1


def build_media_entry(filename, file_stat, url_prefix):
    """构建媒体列表项。"""
    modified_timestamp = file_stat.st_mtime
    return {
        "filename": filename,
        "size": file_stat.st_size,
        "modified_timestamp": modified_timestamp,
        "modified_time": datetime.fromtimestamp(modified_timestamp).strftime("%Y-%m-%d %H:%M:%S"),
        "url": f"{url_prefix}/{filename}",
    }


def get_media_list(media_type):
    """获取指定类型的媒体文件列表。"""
    media_list = []
    if not os.path.exists(UPLOAD_FOLDER):
        return media_list

    media_config = get_media_config(media_type)

    try:
        for filename in os.listdir(UPLOAD_FOLDER):
            if not media_config["allowed"](filename):
                continue
            file_path = os.path.join(UPLOAD_FOLDER, filename)
            if os.path.isfile(file_path):
                media_list.append(
                    build_media_entry(
                        filename=filename,
                        file_stat=os.stat(file_path),
                        url_prefix=media_config["url_prefix"],
                    )
                )

        media_list.sort(
            key=lambda x: (x["modified_timestamp"], x["filename"]),
            reverse=True,
        )

    except Exception as e:
        logger.exception(f"获取{media_config['label']}列表失败: {e}")

    return media_list


def format_size(size_bytes):
    """格式化文件大小。"""
    if size_bytes == 0:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"


create_remote_runner_routes(
    app,
    logger,
    media_list_getter=get_media_list,
    app_config=config,
    page_access_guard=lambda: require_page_access(
        "/remote-runner",
        "Remote Runner - 身份验证",
        "Remote Runner 身份验证",
        "请输入 API 密钥以访问远端 Workflow 运行页面。",
    ),
    api_access_guard=lambda: (None if has_runner_api_access() else (jsonify({"error": "未授权访问"}), 401)),
)


def save_uploaded_file(file_storage, media_type, client_ip):
    """保存上传的文件并返回响应数据。"""
    media_config = get_media_config(media_type)
    original_filename = secure_filename(file_storage.filename)
    new_filename, save_path = build_unique_save_path(generate_filename(original_filename))

    try:
        start = time.time()
        file_storage.save(save_path)
        cost = time.time() - start
        file_size = os.path.getsize(save_path)
        logger.info(
            f"{media_config['label']}上传成功: {new_filename} ({file_size} bytes)，来源IP: {client_ip}"
        )
        return {
            "message": f"{media_config['label']}上传成功",
            "filename": new_filename,
            "size": file_size,
            "path": save_path,
            "cost_seconds": round(cost, 2),
        }, 200
    except Exception as e:
        logger.exception(f"保存{media_config['label']}失败")
        return {
            "error": f"保存{media_config['label']}失败",
            "details": str(e),
        }, 500


def delete_media_file(filename, media_type, client_ip):
    """删除指定媒体文件。"""
    media_config = get_media_config(media_type)
    safe_filename, file_path = resolve_media_path(filename, media_type)

    try:
        os.remove(file_path)
        logger.info(f"{media_config['label']}删除成功: {safe_filename}，来源IP: {client_ip}")
        return {"message": f"{media_config['label']}删除成功", "filename": safe_filename}, 200
    except Exception as e:
        logger.exception(f"删除{media_config['label']}失败")
        return {"error": f"删除{media_config['label']}失败", "details": str(e)}, 500


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

    _, error_response, status_code = require_api_key(client_ip, "图片上传")
    if error_response is not None:
        return error_response, status_code

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
    
    payload, status_code = save_uploaded_file(file, "image", client_ip)
    return jsonify(payload), status_code


@app.route('/health', methods=['GET'])
def health_check():
    """健康检查端点"""
    return jsonify({
        "status": "ok",
        "upload_dir": UPLOAD_FOLDER,
        "config_loaded": os.path.exists(CONFIG_FILE)
    }), 200


@app.route('/images/<filename>', methods=['GET'])
def serve_image(filename):
    """
    提供图片文件访问服务
    
    Args:
        filename: 图片文件名
    
    Returns:
        图片文件或404错误
    """
    # 安全检查：确保文件名安全
    safe_filename, _ = resolve_media_path(filename, "image")
    return send_from_directory(UPLOAD_FOLDER, safe_filename)


@app.route('/videos/<filename>', methods=['GET'])
def serve_video(filename):
    """
    提供视频文件访问服务
    
    Args:
        filename: 视频文件名
    
    Returns:
        视频文件或404错误
    """
    # 安全检查：确保文件名安全
    safe_filename, _ = resolve_media_path(filename, "video")
    
    # 根据文件扩展名设置正确的 MIME 类型
    ext = safe_filename.rsplit('.', 1)[1].lower() if '.' in safe_filename else 'mp4'
    mime_type = VIDEO_MIME_TYPES.get(ext, 'video/mp4')
    
    return send_from_directory(UPLOAD_FOLDER, safe_filename, mimetype=mime_type)


@app.route('/images/<filename>', methods=['DELETE'])
def delete_image(filename):
    """删除图片文件。"""
    client_ip = request.remote_addr
    _, error_response, status_code = require_api_key(client_ip, "删除图片")
    if error_response is not None:
        return error_response, status_code

    payload, status_code = delete_media_file(filename, "image", client_ip)
    return jsonify(payload), status_code


@app.route('/videos/<filename>', methods=['DELETE'])
def delete_video(filename):
    """删除视频文件。"""
    client_ip = request.remote_addr
    _, error_response, status_code = require_api_key(client_ip, "删除视频")
    if error_response is not None:
        return error_response, status_code

    payload, status_code = delete_media_file(filename, "video", client_ip)
    return jsonify(payload), status_code


@app.route('/view', methods=['GET', 'POST'])
def view_images():
    """
    图片和视频预览页面
    
    根据配置决定是否启用该功能，需要API密钥验证
    """
    # 检查是否启用预览功能
    if not config.get("enable_view", False):
        return jsonify({
            "error": "预览功能未启用",
            "message": "请在 config.json 中设置 enable_view 为 true 以启用此功能"
        }), 404
    
    access_response = require_page_access(
        "/view",
        "媒体预览 - 身份验证",
        "媒体预览身份验证",
        "请输入 API 密钥以访问图片和视频预览页面。",
    )
    if access_response is not None:
        return access_response
    
    # 获取图片和视频列表
    image_list = get_media_list("image")
    video_list = get_media_list("video")
    
    # 计算总大小
    total_size = sum(img["size"] for img in image_list) + sum(vid["size"] for vid in video_list)
    
    # 为每个图片添加格式化的大小
    for img in image_list:
        img["size_formatted"] = format_size(img["size"])
    
    # 为每个视频添加格式化的大小
    for vid in video_list:
        vid["size_formatted"] = format_size(vid["size"])
    
    # 渲染HTML模板
    return render_template(
        'view.html',
        image_list=image_list,
        video_list=video_list,
        image_count=len(image_list),
        video_count=len(video_list),
        total_size=format_size(total_size),
        default_tab="image" if image_list or not video_list else "video",
    )

@app.route('/upload_video', methods=['POST'])
def upload_video():
    client_ip = request.remote_addr
    logger.info(f"Video upload request from {client_ip}")

    _, error_response, status_code = require_api_key(client_ip, "视频上传")
    if error_response is not None:
        return error_response, status_code

    if 'file' not in request.files:
        return jsonify({"error": "No file"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Empty filename"}), 400

    if not allowed_video(file.filename):
        return jsonify({
            "error": "Invalid video type",
            "allowed": list(ALLOWED_VIDEO_EXTENSIONS)
        }), 400

    payload, status_code = save_uploaded_file(file, "video", client_ip)
    return jsonify(payload), status_code

@app.route('/', methods=['GET'])
def index():
    """根路径，返回服务信息"""
    endpoints = {
        "upload": "/upload (POST)",
        "health": "/health (GET)",
        "remote_runner": "/remote-runner (GET)",
    }
    
    # 如果启用了预览功能，添加到端点列表
    if config.get("enable_view", False):
        endpoints["view"] = "/view (GET)"
    
    return jsonify({
        "service": "ComfyUI Remote Image Upload Server",
        "version": "1.0.0",
        "endpoints": endpoints
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
