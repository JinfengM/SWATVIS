# SWATVIS 1.2.1 for Windows

[Download SWATVIS1.2.1-setup.exe](https://github.com/JinfengM/SWATVIS/raw/refs/heads/main/setup/SWATVIS1.2.1-setup.exe) · Windows x64 · 608 MB

The offline installer includes PostgreSQL 16.10, PostGIS 3.7.0, and the GeoServer and Python runtimes. The setup wizard is in English. The application supports English and Chinese.

## Install and run

1. Download `SWATVIS1.2.1-setup.exe`, run it, and approve Windows administrator elevation.
2. If Setup finds an existing PostgreSQL installation, choose whether to use it or install the independent bundled instance. To use the bundled database, choose **No** when asked whether to use the existing installation.
3. Open SWATVIS. For a new user profile, the bundled connection is filled automatically. If you chose your own PostgreSQL instance, enter its port, database, username, and password in **Database settings** and select **Test and save**.
4. Select a model directory containing `output.hru` and `file.cio` from the same simulation. If SWATVIS cannot automatically find matching HRU geometry, select the HRU boundary Shapefile. Select your variables and temporal scale, then click **Import and publish**.

## If the connection on port 5432 fails

The bundled instance uses an available local port. Setup can choose another port, such as `5433`, if `5432` is occupied or reserved by another installation. A previously saved connection may still point to `5432`.

1. Open **Database settings** in SWATVIS.
2. Click **Use the bundled database**. SWATVIS loads the bundled port and credentials, tests the connection, and saves it on success.
3. Close the dialog after the PostGIS connection test succeeds, then run **Import and publish**.

The button is available when the bundled instance was configured for your Windows account. If you chose to reuse an existing instance, use its connection details or rerun Setup and choose the bundled instance.

## 中文安装说明

1. 下载并运行 `SWATVIS1.2.1-setup.exe`，确认 Windows 管理员授权。
2. 如果安装器询问是否使用现有 PostgreSQL，选择 **Yes** 可继续使用现有数据库，选择 **No** 可安装独立的随附数据库。
3. 打开 SWATVIS，选择同时包含 `output.hru` 和 `file.cio` 的模型目录。按需指定 HRU 边界 Shapefile，然后选择指标和时间尺度，点击「导入并发布」。

### 默认 5432 端口连接失败

随附数据库可能使用其他端口，例如 `5433`。如果软件仍在尝试旧连接，请打开「数据库设置」，点击 **Use the bundled database（使用随附数据库）**。客户端会自动读取正确的端口和账号密码，在测试成功后保存。首次安装时若选择了复用现有数据库，可填写该数据库的实际连接参数，或重新运行安装包选择独立的随附数据库。

## Installer checksum

SHA-256 `2d874b2e66b3c75948e4797d70dcb5da79158cb8ad3d9f84c7c815743ed71e47`
