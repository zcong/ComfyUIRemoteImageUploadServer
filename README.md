# ComfyUI远程图片上传服务端

这是ComfyUI远程图片上传功能的服务端程序，用于接收和保存来自ComfyUI节点的图片上传请求。

## 功能特性

- ✅ HTTP POST接口接收文件上传
- ✅ X-API-KEY header身份验证
- ✅ 可配置端口（默认65360）
- ✅ 文件自动命名：`comfyui_` + 8位随机数 + 扩展名
- ✅ 完整的错误处理和日志记录
- ✅ 支持配置文件或命令行参数
- ✅ 图片预览功能（可选，通过配置启用）

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置服务端

编辑 `config.json` 文件，设置你的API密钥：

```json
{
    "port": 65360,
    "api_key": "your_secret_key_here",
    "upload_dir": "images",
    "max_file_size": 52428800,
    "enable_view": false
}
```

**重要**：请将 `api_key` 修改为你自己的密钥，不要使用默认值！

### 3. 启动服务端

```bash
python upload_server.py
```

或者使用命令行参数：

```bash
python upload_server.py --port 65360 --api-key your_secret_key_here
```

## 配置说明

### config.json 配置项

- **port**: 服务端口，默认65360
- **api_key**: API验证密钥，必须与ComfyUI节点中输入的密钥一致
- **upload_dir**: 上传文件保存目录，相对于server目录的父目录
- **max_file_size**: 最大文件大小（字节），默认50MB
- **enable_view**: 是否启用图片预览功能，默认false。设置为true后，可通过浏览器访问 `/view` 路径查看上传的图片列表

### 命令行参数

```bash
python upload_server.py [选项]

选项:
  --port PORT        服务端口（默认：从config.json读取）
  --host HOST        监听地址（默认：0.0.0.0）
  --api-key KEY      API密钥（会覆盖配置文件中的设置）
  --debug            启用调试模式
```

## API接口

### POST /upload

上传图片文件

**请求头**:
- `X-API-KEY`: API密钥（必需）

**请求体**:
- `multipart/form-data` 格式
- 字段名：`file`
- 支持的文件类型：png, jpg, jpeg, gif, webp, bmp

**响应示例**:

成功 (200):
```json
{
    "message": "文件上传成功",
    "filename": "comfyui_a3f5b2c1.png",
    "size": 123456,
    "path": "/path/to/images/comfyui_a3f5b2c1.png"
}
```

失败 (401):
```json
{
    "error": "API密钥无效"
}
```

### GET /health

健康检查端点

**响应**:
```json
{
    "status": "ok",
    "upload_dir": "/path/to/images",
    "config_loaded": true
}
```

### GET /

服务信息

**响应**:
```json
{
    "service": "ComfyUI Remote Image Upload Server",
    "version": "1.0.0",
    "endpoints": {
        "upload": "/upload (POST)",
        "health": "/health (GET)",
        "view": "/view (GET)"
    }
}
```

### GET /view

图片预览页面（需要启用 `enable_view` 配置和API密钥验证）

**说明**：
- 仅在 `config.json` 中设置 `"enable_view": true` 时可用
- **需要API密钥验证**：必须提供正确的API密钥才能访问
- 返回HTML页面，展示所有已上传的图片
- 支持缩略图浏览和点击查看大图
- 显示图片统计信息（总数、总大小）

**访问方式**：

1. **通过浏览器访问**（推荐）：
   - 在浏览器中打开：`http://localhost:65360/view`（端口根据配置而定）
   - 系统会显示密钥输入页面，输入正确的API密钥后即可访问

2. **通过URL参数传递密钥**：
   ```
   http://localhost:65360/view?key=your_api_key_here
   ```

3. **通过请求头传递密钥**：
   ```
   X-API-KEY: your_api_key_here
   ```

**响应**：
- 如果功能已启用且密钥正确：返回HTML预览页面
- 如果功能已启用但未提供密钥：返回密钥输入页面
- 如果功能已启用但密钥错误：返回密钥输入页面并显示错误提示
- 如果功能未启用：返回404错误和提示信息

### GET /images/<filename>

直接访问图片文件

**说明**：
- 用于在预览页面中显示图片
- 支持所有允许的图片格式（png, jpg, jpeg, gif, webp, bmp）
- 包含安全检查，防止路径遍历攻击

**示例**：
```
http://localhost:65360/images/comfyui_a3f5b2c1.png
```

## 图片预览功能

### 启用预览功能

1. 编辑 `config.json` 文件，设置 `"enable_view": true`
2. 重启服务端
3. 在浏览器中访问 `http://localhost:65360/view`（端口根据配置而定）
4. 输入正确的API密钥（与 `config.json` 中的 `api_key` 一致）进行验证

### 功能特点

- 📸 **缩略图网格展示**：以响应式网格布局展示所有图片
- 🔍 **点击查看大图**：点击缩略图可在模态框中查看完整图片
- 📊 **统计信息**：显示图片总数和总大小
- 📱 **响应式设计**：适配桌面和移动设备
- ⚡ **懒加载**：图片使用懒加载技术，提升页面性能
- 🎨 **现代化UI**：美观的渐变背景和流畅的动画效果

### 安全说明

- 预览功能默认关闭，需要手动在配置中启用
- **API密钥验证**：访问预览页面必须提供正确的API密钥，防止未授权访问
- 密钥可以通过URL参数（`?key=xxx`）或请求头（`X-API-KEY`）传递
- 建议在生产环境中使用HTTPS，避免密钥在URL中明文传输
- 建议定期更换API密钥以提高安全性

## 文件命名规则

上传的文件会自动命名为：`comfyui_` + 8位随机字符串 + 原始扩展名

例如：
- `comfyui_a3f5b2c1.png`
- `comfyui_9x8k7m2n.jpg`

如果文件名冲突，会自动添加时间戳后缀。

## 日志

服务端会记录详细的日志到 `upload_server.log` 文件，包括：
- 请求来源IP
- API密钥验证结果
- 文件保存状态
- 错误详情

同时也会输出到控制台。

## 安全建议

1. **修改默认API密钥**：务必在 `config.json` 中设置强密码
2. **使用HTTPS**：在生产环境中，建议使用HTTPS（需要配置SSL证书）
3. **防火墙配置**：只允许必要的IP访问服务端端口
4. **定期更新密钥**：定期更换API密钥以提高安全性

## 故障排查

### 服务端无法启动

1. 检查端口是否被占用：`lsof -i :65360`
2. 检查Python依赖是否安装完整：`pip install -r requirements.txt`
3. 查看服务端日志文件 `upload_server.log`

### 文件上传失败

1. 检查上传目录的写入权限
2. 检查磁盘空间是否充足
3. 检查文件大小是否超过限制
4. 查看服务端日志获取详细错误信息

## 许可证

MIT License

