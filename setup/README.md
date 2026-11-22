# SWATVIS 1.2.1 for Windows

[Download SWATVIS1.2.1-setup.exe](https://github.com/JinfengM/SWATVIS/raw/refs/heads/main/setup/SWATVIS1.2.1-setup.exe) · Windows x64 · 590 MB

The offline installer includes PostgreSQL 16.10, PostGIS 3.7.0, and the GeoServer and Python runtimes. The setup wizard is in English. The application supports English and Chinese.

## Install and run

1. Download `SWATVIS1.2.1-setup.exe`, run it, and approve Windows administrator elevation.
2. If Setup finds an existing PostgreSQL installation, choose whether to use it or install the independent bundled instance. To use the bundled database, choose **No** when asked whether to use the existing installation.
3. Open SWATVIS. For a new user profile, the bundled connection is filled automatically. If you chose your own PostgreSQL instance, enter its port, database, username, and password in **Database settings** and select **Test and save**.
4. Select a model directory containing `output.hru` and `file.cio` from the same simulation. If SWATVIS cannot automatically find matching HRU geometry, select the HRU boundary Shapefile. Select your variables and temporal scale, then click **Import and publish**.

## Try the example dataset

1. Download and extract the repository ZIP, then locate `SWATVIS-main/setup/example`. It contains `output.hru`, `file.cio`, and the `geometry` folder. Keep the Shapefile and its companion files together inside `geometry`. [Download repository ZIP](https://github.com/JinfengM/SWATVIS/archive/refs/heads/main.zip)
2. In SWATVIS, under **Model inputs**, click **Select directory** and select the extracted `setup/example` folder. SWATVIS should find `geometry/fullhru.shp` and select `HRUGIS` automatically. If needed, click **Select file** next to **HRU boundary**, choose `geometry/fullhru.shp`, and set **HRU identifier field** to `HRUGIS`.
3. Set **Variable** to **Surface runoff generation (SURQ_GEN)** and **Temporal scale** to **Monthly**. Set **Run mode** to **Import and publish**, then click **Import and publish**. If the database connection fails on port `5432`, follow the instructions in the next section.
4. When **Publication complete** appears, use the map's time slider or **Play time series** to explore the results, or select **Compare two dates** to view two dates side by side. This example includes 364 HRUs and covers 2009–2018, with 120 monthly and 10 annual time steps.

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

### 使用示例数据

1. 下载并解压仓库 ZIP，找到解压后的 `SWATVIS-main/setup/example`。该目录包含 `output.hru`、`file.cio` 和 `geometry` 文件夹。请将 Shapefile 及其配套文件保留在 `geometry` 中。[下载仓库 ZIP](https://github.com/JinfengM/SWATVIS/archive/refs/heads/main.zip)
2. 打开 SWATVIS，在「模型输入」中点击「选择目录」，选择解压后的 `setup/example` 文件夹。软件会自动查找 `geometry/fullhru.shp` 并匹配 `HRUGIS` 字段。如果未自动识别，在「HRU 边界」旁点击「选择文件」，选择 `geometry/fullhru.shp`，并将「HRU 编号字段」设为 `HRUGIS`。
3. 将「指标」设为「地表径流产生量（SURQ_GEN）」，将「时间尺度」设为「月尺度」。将「运行方式」设为「导入并发布」，然后点击「导入并发布」。如果 `5432` 端口连接失败，按下一节处理。
4. 看到「发布完成」后，可用地图时间滑块或「播放时间序列」查看结果，也可用「双图时点对比」并排查看两个时点。示例包含 364 个 HRU，覆盖 2009–2018 年，提供 120 个逐月时点和 10 个逐年时点。

### 默认 5432 端口连接失败

随附数据库可能使用其他端口，例如 `5433`。如果软件仍在尝试旧连接，请打开「数据库设置」，点击 **Use the bundled database（使用随附数据库）**。客户端会自动读取正确的端口和账号密码，在测试成功后保存。首次安装时若选择了复用现有数据库，可填写该数据库的实际连接参数，或重新运行安装包选择独立的随附数据库。

## Installer checksum

SHA-256 `5921ee8148d1e8ac828293f843f0547f4d42ebd8902226dea9205605e52f14b0`
