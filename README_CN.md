# FKFTP

一个极简的 FTP 服务器，带 Web 管理界面。

## 为什么做这个？

在局域网内拷贝文件，本来应该是一件很简单的事。但 Windows 11 收紧了 SMB 共享的安全策略，再加上微软账户登录本地机器后，网络共享的认证、权限配置变得异常繁琐——折腾了很久都没搞定。

于是决定自己写一个 FTP 服务器：**不需要折腾 Windows 共享策略，打开就能用，配置全靠网页界面点点就行。**

## 功能

- **Web 管理界面** — 浏览器打开即可配置，不用改配置文件
- **多目录挂载** — 每个用户可以映射多个不同盘符的目录，FTP 客户端看到统一的虚拟目录树
- **SHA-256 密码加密** — 密码不以明文存储
- **精细权限控制** — 按用户设置读取、上传、删除、重命名等 8 项权限
- **防火墙一键配置** — 在 Web 界面直接添加/移除 Windows 防火墙规则
- **Windows 服务** — 可注册为系统服务，开机自动启动
- **单文件部署** — PyInstaller 打包成一个可执行文件，拷到任意机器直接运行
- **跨平台** — 支持 Windows、macOS、Linux
- **多语言界面** — Web UI 支持中文和英文切换

## 快速开始

### 直接运行

```
fkftp.exe
```

浏览器自动打开 `http://127.0.0.1:8080` 管理界面。

### 从源码运行

```bash
pip install -r requirements.txt
python app.py
```

### 打包

Windows:
```bash
build.bat
```

macOS / Linux:
```bash
chmod +x build.sh
./build.sh
```

生成的可执行文件在 `dist/` 目录下。

> **说明：** 防火墙管理和 Windows 服务功能仅在 Windows 上可用，在 macOS/Linux 上这些面板会自动隐藏。FTP 服务器核心功能在所有平台上完全一致。

## 使用流程

1. 运行 `fkftp.exe`（或 `python app.py`）
2. 在 Web 界面添加用户，设置密码和权限
3. 为用户配置目录映射（可映射多个不同盘符的文件夹）
4. 保存配置，启动 FTP 服务
5. 用任意 FTP 客户端（Windows 资源管理器、FileZilla 等）连接

## FTP 客户端连接

在 Windows 资源管理器地址栏输入：

```
ftp://你的IP:2121
```

或使用 FileZilla 等客户端连接。

## 注册为 Windows 服务

> 此功能仅适用于 Windows。

在 Web 界面点击"安装服务"，或通过命令行：

```bash
fkftp.exe --service install   # 安装（需管理员权限）
fkftp.exe --service start     # 启动
fkftp.exe --service stop      # 停止
fkftp.exe --service uninstall # 卸载
```

## 项目结构

```
app.py           # Flask Web 管理后端
server.py        # FTP 服务器核心（pyftpdlib）
filesystem.py    # 多目录虚拟文件系统
service.py       # Windows 服务注册（仅 Windows）
hash_password.py # 密码哈希工具
config.json      # 运行时配置（自动生成）
build.bat        # Windows 打包脚本
build.sh         # macOS/Linux 打包脚本
templates/
  index.html     # Web 管理界面（单页应用）
tests/           # 单元测试
```

## 依赖

- [pyftpdlib](https://github.com/giampaolo/pyftpdlib) — FTP 服务器库
- [Flask](https://flask.palletsprojects.com/) — Web 框架
- [PyInstaller](https://pyinstaller.org/) — 打包工具

## License

MIT
