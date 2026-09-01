# Raspberry Pi 5 本地多模态桌面 AI 助手

在 Raspberry Pi 5 8GB 上完成一条本地优先的中英双语交互链路：

```text
网页按键 → USB 麦克风 → whisper.cpp 中英 ASR
                              │
文本输入 / 明确视觉口令 ──────┼→ 按需拍照 → Ollama + Qwen 3.5 → Piper 中英 TTS
                              │                         │
                              └──── FastAPI 网页、状态、耗时、SQLite 历史 ────┘
```

本仓库包含应用源码、网页、systemd 配置、审计/安装脚本、Mac 弱网中转脚本、硬件测试和基准工具。**不包含模型、真实录音、照片、IP 地址或访问口令。**

> ⚠️ **ATTENTION**
>
> - 目标设备是 Raspberry Pi 5 8GB、64 位 Raspberry Pi OS、64GB microSD、USB 麦克风和官方摄像头。
> - 实机链路验证日期：2026-08-25；已验证的 Ollama 版本为 `0.32.15`，模型为 `qwen3.5:2b`。
> - 安装脚本只执行 `apt update` 和安装明确列出的必要包，**不会执行 `apt upgrade` 或发行版升级**。
> - 默认不依赖大容量 SD swap；先保留旧 swap 做观察，目标是正常交互不产生持续 swap 抖动。
> - 当前拍照由网页开关或明确中英文口令触发，不允许小模型随意打开摄像头。

## 功能与边界

- 默认模型：`qwen3.5:2b`，4K 上下文、非思考模式、最多约 192 个输出 token。
- 对照模型：`qwen3.5:4b`，只在手动勾选对照时使用，不与 2B 同时常驻。
- 图像输入：默认拍摄并压缩到 640×480；需要更多细节时可改成 1024×768，但延迟会明显增加。
- 视觉触发：网页“附带当前画面”开关，或“看看、拍照、摄像头、what do you see、take a photo、camera”等明确口令。
- TTS：Piper 中文、英文 voice 常驻；中英混合回复按片段分别合成并依次播放。
- 状态机：`IDLE → RECORDING → TRANSCRIBING → CAPTURING（可选）→ THINKING → SPEAKING → IDLE/ERROR`。
- 并发：同一时刻只允许一个任务，忙碌时返回 HTTP `409`，不堆积无上限队列。
- 隐私：录音和照片位于运行时临时目录，处理后删除；SQLite 只保存文字、模型、耗时、内存、温度和错误码。
- 降级：摄像头失败时继续文本问答；TTS/本机播放失败时保留网页文字和临时音频；Ollama 出错会卸载当前模型并恢复可操作状态。

## 仓库结构

```text
src/pi_edge_assistant/        FastAPI、状态机、硬件与推理服务
src/pi_edge_assistant/static/ 原生 HTML/CSS/JavaScript 网页
deploy/                       systemd、Ollama 限制与配置模板
scripts/                      审计、备份、安装、模型及硬件脚本
benchmarks/                   ASR、多模态、稳定性及云对照工具
tests/                        不依赖树莓派硬件的自动化测试
docs/wechat-article.md        可直接排版的公众号总结稿
```

---

## Step 1：准备系统与硬件

### 1.1 系统要求

推荐使用 Raspberry Pi Imager 写入 64 位 Raspberry Pi OS，并在烧录时配置用户名、Wi-Fi 和 SSH。现代系统不应再假定默认用户名/密码是 `pi/raspberry`。

登录树莓派：

```bash
ssh 你的用户名@树莓派IP
```

确认架构：

```bash
dpkg --print-architecture
uname -m
```

应分别看到 `arm64` 和 `aarch64`。

📌 **系统版本策略**

- 健康的 64 位 Bookworm 可以原地维护，不必为了本项目升级系统。
- 若确实需要跨到 Trixie，先备份再重新烧录。不要把“部署 AI 助手”和“跨大版本升级”混成一次变更。
- 摄像头从 Bookworm 起使用 `rpicam-*`；旧教程里的 `libcamera-*` 名称不再是首选。

### 1.2 接线

- USB 麦克风接入任意稳定的 USB 口。
- 摄像头接到 CAM/DISP 接口。先提起接口锁扣，插入排线，再压回锁扣，不要硬塞。
- 使用官方 27W 电源或稳定的 5V/5A 电源，并配置主动散热。

---

## Step 2：克隆代码，先审计旧环境

```bash
cd ~
git clone https://github.com/83900/raspberry-pi5-multimodal-assistant.git pi-edge-assistant
cd ~/pi-edge-assistant
```

不要先删除旧 Ollama、Whisper、模型或 swap。先生成审计和备份：

```bash
./scripts/audit_pi.sh
./scripts/backup_old_environment.sh
```

审计报告默认写入 `~/pi-edge-assistant/audit/`，备份默认写入 `~/pi-edge-backups/`。备份只保存脚本、配置、服务文件和模型清单，不重复复制可重新下载的大模型。

重点检查：

```bash
free -h
swapon --show
findmnt --target /mnt/swapfile
vcgencmd measure_temp
vcgencmd get_throttled
ollama --version
ollama list
```

💡 **Tip：**`df -h` 只能查看文件系统，不能证明 swap 已启用。若 `/mnt` 没有单独磁盘挂载，`/mnt/swapfile` 仍然写在 microSD 根分区。

---

## Step 3：安装必要依赖和应用

```bash
cd ~/pi-edge-assistant
./scripts/install_pi.sh
```

脚本只安装以下必要系统包：

```text
python3-venv python3-dev build-essential cmake git curl
ffmpeg alsa-utils rpicam-apps python3-picamera2
```

随后会：

1. 创建带 system site packages 的 `.venv`，以便复用 Raspberry Pi OS 提供的 Picamera2。
2. 在虚拟环境安装 FastAPI、Piper、Pillow 等 Python 依赖。
3. 创建 `~/.config/pi-edge-assistant/edge-assistant.env`。
4. 安装并启用当前用户的 systemd 服务，但不立即启动应用。

**不会使用 `pip --break-system-packages`，不会执行 `apt upgrade`。**

---

## Step 4：安装 Ollama

如果树莓派已经能运行 `ollama --version`，跳过安装，只执行本节 4.3。

### 4.1 网络正常：使用官方安装方式

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### 4.2 树莓派网络不稳定：在 Mac 下载后传输

在 Mac 执行，Mac 不需要安装 Ollama：

```bash
cd ~/Downloads
curl -L https://ollama.com/download/ollama-linux-arm64.tgz \
  -o ollama-linux-arm64.tgz
scp ollama-linux-arm64.tgz 你的用户名@树莓派IP:~/pi-edge-assistant/
```

回到树莓派执行：

```bash
cd ~/pi-edge-assistant
./scripts/install_ollama_arm64_archive.sh ./ollama-linux-arm64.tgz
```

该脚本会把 ARM64 包解压到 `/usr`，创建专用 `ollama` 系统用户和 systemd 服务。若系统已存在 Ollama 服务，脚本会拒绝覆盖，请先审计旧服务。

### 4.3 限制 Ollama 内存和监听范围

```bash
./scripts/install_ollama_limits.sh
```

写入的限制为：

```ini
OLLAMA_HOST=127.0.0.1:11434
OLLAMA_MAX_LOADED_MODELS=1
OLLAMA_NUM_PARALLEL=1
OLLAMA_KEEP_ALIVE=5m
```

这能避免两个模型同时驻留，也不会把 Ollama API 暴露到局域网或公网。

---

## Step 5：准备 Qwen 3.5 模型

[Ollama 模型库](https://ollama.com/library/qwen3.5/tags)中，`qwen3.5:2b` 约 2.7GB、`qwen3.5:4b` 约 3.4GB，二者都接受文本和图像输入。这里仍主动限制到 4K 上下文，而不是使用模型标称的超长上下文，以控制树莓派内存。

### 5.1 直接在树莓派拉取

只安装日常 2B：

```bash
./scripts/setup_models.sh
```

同时安装 4B 对照：

```bash
./scripts/setup_models.sh --compare
```

### 5.2 用 Mac 下载模型 bundle，再传给树莓派

Mac 不需要 Ollama，只需要 Python 3：

```bash
cd ~/Downloads
python3 ~/你的代码目录/pi-edge-assistant/scripts/download_ollama_model.py \
  qwen3.5:2b qwen3.5-2b

# 4B 只在需要做对照时下载
python3 ~/你的代码目录/pi-edge-assistant/scripts/download_ollama_model.py \
  qwen3.5:4b qwen3.5-4b
```

脚本支持断点续传并对每个 blob 做 SHA-256 校验。传输：

```bash
rsync -avP ~/Downloads/qwen3.5-2b/ \
  你的用户名@树莓派IP:~/qwen3.5-2b/
```

树莓派安装 bundle：

```bash
cd ~/pi-edge-assistant
./scripts/install_ollama_model_bundle.sh ~/qwen3.5-2b
ollama list
```

📌 **注意：**模型文件不会上传到本 GitHub 仓库；Git 只保存下载与安装脚本。

---

## Step 6：构建 whisper.cpp 和量化模型

```bash
cd ~/pi-edge-assistant
./scripts/setup_whisper.sh
```

脚本使用当前 CMake 流程，程序位于：

```text
~/whisper.cpp/build/bin/whisper-cli
```

脚本下载多语言 `base`、`small` 并生成 `ggml-base-q5_0.bin` 和 `ggml-small-q5_0.bin`。

默认先用 base。只有固定 24 条录音测试中，small 的综合错误率相对改善至少 10%，且实时系数 RTF 不超过 1.0，才切到 small。

💡 whisper.cpp 官方文档说明量化可以降低模型磁盘和内存占用；第一版按键录音已经限定语音区间，因此不把 VAD 作为启动前置条件。

---

## Step 7：下载 Piper 中英文语音

```bash
cd ~/pi-edge-assistant
./scripts/setup_tts.sh
```

默认语音：

- 中文：`zh_CN-huayan-medium.onnx`
- 英文：`en_US-lessac-medium.onnx`

每个 voice 必须同时有 `.onnx` 和 `.onnx.json`。不同 voice 可能有各自许可条件，公开分发前请查看相应 model card；本仓库不重新分发 voice 文件。

测试中文：

```bash
echo '你好，这是树莓派本地语音测试。' | \
  .venv/bin/python -m piper \
  -m ~/.local/share/piper/zh_CN-huayan-medium.onnx \
  -f /tmp/piper-zh.wav
aplay /tmp/piper-zh.wav
```

应用会缓存已经加载的中英文 voice，避免每个句子重新载入模型。

---

## Step 8：验证摄像头、麦克风和扬声器

```bash
rpicam-hello --list-cameras
rpicam-still --nopreview --immediate -o /tmp/camera-test.jpg
arecord -l
arecord -L
aplay -l
aplay -L
./scripts/smoke_test_hardware.sh
```

若 `default` 不是 USB 麦克风，可临时指定：

```bash
AUDIO_CAPTURE_DEVICE=plughw:2,0 \
AUDIO_PLAYBACK_DEVICE=default \
./scripts/smoke_test_hardware.sh
```

设备编号可能在重启后变化，长期配置优先使用 `arecord -L` 和 `aplay -L` 中的稳定名称。

---

## Step 9：检查应用配置

```bash
nano ~/.config/pi-edge-assistant/edge-assistant.env
```

关键配置：

```ini
EDGE_HOST=0.0.0.0
EDGE_PORT=8080
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3.5:2b
OLLAMA_COMPARE_MODEL=qwen3.5:4b
OLLAMA_CONTEXT=4096
OLLAMA_MAX_TOKENS=192
WHISPER_CLI=/home/你的用户名/whisper.cpp/build/bin/whisper-cli
WHISPER_MODEL=/home/你的用户名/whisper.cpp/models/ggml-base-q5_0.bin
AUDIO_CAPTURE_DEVICE=default
AUDIO_PLAYBACK_DEVICE=default
PIPER_ZH_VOICE=/home/你的用户名/.local/share/piper/zh_CN-huayan-medium.onnx
PIPER_EN_VOICE=/home/你的用户名/.local/share/piper/en_US-lessac-medium.onnx
TTS_ENABLED=true
CAMERA_WIDTH=640
CAMERA_HEIGHT=480
MEDIA_TTL_SECONDS=600
```

安装脚本会自动把模板里的 home 和用户 UID 替换成当前值，通常只需调整音频设备。

---

## Step 10：启动服务并打开网页

```bash
systemctl --user start pi-edge-assistant
systemctl --user status pi-edge-assistant --no-pager
journalctl --user -u pi-edge-assistant -f
```

首次启动会生成随机访问口令：

```bash
cat ~/.local/share/pi-edge-assistant/access-token
hostname -I
```

在同一局域网的电脑或手机打开：

```text
http://树莓派IP:8080
```

输入访问口令后即可使用：

- 点击“开始说话”，使用的是树莓派上的 USB 麦克风。
- 点击“停止并识别”，网页会显示转写、状态、回复和各阶段耗时。
- 输入普通文字可直接问答。
- 勾选“附带当前画面”会强制拍照。
- 不勾选时，输入 `take a photo and describe it in Chinese` 也会由明确规则触发拍照，然后用中文回答。
- “停止播报”用于立即终止树莓派音频播放。
- 本机播放失败时，可使用网页中的临时音频回退。

⚠️ 不要把 8080 或 11434 映射到公网。访问口令只是局域网轻量保护，不替代 HTTPS、反向代理和正式身份认证。

---

## 可选：微雪 4.3 英寸 DSI 触摸屏 kiosk

适用于已经能正常显示和触控的横向 800×480 `4.3inch DSI LCD/QLED`。安装器不会修改 DSI overlay、旋转、触控映射、摄像头、模型、swap 或风扇配置。

```bash
cd ~/pi-edge-assistant
./scripts/install_kiosk.sh
```

安装器会：

- 检查当前显示输出和触控设备，仅输出诊断信息。
- 复用现有 Chromium；只有浏览器不存在时才执行 `apt update` 并安装对应 Chromium 包，不执行 `apt upgrade`。
- 设置当前用户的 Raspberry Pi OS 桌面自动登录。
- 在桌面和应用菜单创建“树莓派本地助手”启动图标，不再开机自动弹出 Chromium。
- 点击图标后打开 `http://127.0.0.1:8080/?display=1`。
- 使用独立浏览器 profile、单实例锁和崩溃重启循环。
- 在触摸模式申请 Screen Wake Lock；X11 环境同时关闭 DPMS。

触摸界面使用底部三页签：

- **助手**：录音、附带画面、4B 对照、停止播报、折叠文字输入、转写和回复。
- **画面 / 状态**：最后照片、模型、温度、内存、swap、磁盘和阶段耗时。
- **历史**：最近 30 条文本记录和清空历史。

顶部“退出”按钮关闭本机全屏界面。若录音、转写、拍照、推理或播报尚未结束，界面必须二次确认；退出只关闭显示窗口，后台任务、FastAPI、Ollama 和局域网页面继续运行。

本机界面通过回环地址取得临时 display token，不读取或保存主访问口令；临时 token 离开回环连接后无效。局域网普通网页仍需原访问口令。

SSH 运维命令：

```bash
./scripts/kiosk_control.sh status
./scripts/kiosk_control.sh pause
./scripts/kiosk_control.sh resume
./scripts/kiosk_control.sh restart
./scripts/kiosk_control.sh logs
```

暂停或重启 Chromium 不会停止 FastAPI、Ollama 或局域网页面。若点击桌面图标后没有打开全屏界面，先检查：

```bash
curl http://127.0.0.1:8080/api/health
systemctl --user status pi-edge-assistant --no-pager
./scripts/kiosk_control.sh status
./scripts/kiosk_control.sh logs
```

---

## Step 11：验证 API

```bash
token="$(cat ~/.local/share/pi-edge-assistant/access-token)"
curl -H "X-Access-Token: $token" http://127.0.0.1:8080/api/status
curl -X POST http://127.0.0.1:8080/api/chat \
  -H "X-Access-Token: $token" \
  -H 'Content-Type: application/json' \
  -d '{"text":"take a photo and describe it in Chinese","include_image":false}'
```

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/health` | 仅返回服务存活状态，无需鉴权 |
| `POST` | `/api/display/session` | 仅允许回环来源创建临时屏幕会话 |
| `POST` | `/api/display/exit` | 仅允许本机显示会话退出；忙碌时要求确认 |
| `POST` | `/api/recording/start` | 开始树莓派麦克风录音 |
| `POST` | `/api/recording/stop` | 停止录音并异步处理 |
| `POST` | `/api/chat` | 文本问答，可指定图像或 4B 对照 |
| `GET` | `/api/jobs/{id}` | 查询异步任务结果 |
| `GET` | `/api/status` | 状态、模型、温度、内存、swap 和耗时 |
| `GET` | `/api/history` | 最近文字和指标历史 |
| `DELETE` | `/api/history` | 清空历史 |
| `POST` | `/api/playback/stop` | 停止本机播报 |
| `WS` | `/api/events` | 状态、转写、照片、回复、音频和错误事件 |

除健康检查和仅限回环的显示会话外，所有 `/api/*` 请求都需要访问口令。显示退出接口只接受回环来源的临时 display token。WebSocket 连接后的第一条 JSON 消息也必须发送 token。

---

## Step 12：实机结果与参数选择

以下是同一台 Raspberry Pi 5 8GB 上的工程验证，不是所有设备的保证值：

| 场景 | 配置 | 观察结果 |
|---|---|---|
| 纯文本冷启动 | Qwen 3.5 2B | 约 21.3 秒，其中模型加载约 7.7 秒 |
| 纯文本热态 | Qwen 3.5 2B、短回复 | 约 5.5 秒 |
| 视觉热态 | 1024×768 | 约 59.7 秒 |
| 视觉热态 | 640×480 | 约 24.4 秒 |
| 完整英文视觉口令 | 自动拍照、中文回复、TTS | 成功；冷模型 LLM 约 42 秒，TTS 约 6.1 秒 |
| 资源 | 2B 视觉链路 | 峰值内存约 4.5–4.6GB、swap 0、最高约 58.4°C、无降频 |

因此发布默认值使用 640×480。第一次请求包含模型载入，不能和后续热态请求直接比较；正式报告应同时记录 `load_duration`、LLM 总耗时和完整链路耗时。

4B 已作为配置和下载选项加入，但应先完成固定测试集后再评价。不要只因为模型更大就把它设为默认。

---

## Step 13：温度与风扇策略（可选）

如果使用 Raspberry Pi 5 官方主动散热器或兼容 PWM 风扇，可把较晚启动的风扇曲线改得积极一些。编辑：

```bash
sudo nano /boot/firmware/config.txt
```

在 `[all]` 下加入或调整：

```ini
dtparam=fan_temp0=45000
dtparam=fan_temp0_hyst=5000
dtparam=fan_temp0_speed=75
dtparam=fan_temp1=55000
dtparam=fan_temp1_hyst=5000
dtparam=fan_temp1_speed=125
dtparam=fan_temp2=65000
dtparam=fan_temp2_hyst=5000
dtparam=fan_temp2_speed=175
dtparam=fan_temp3=70000
dtparam=fan_temp3_hyst=5000
dtparam=fan_temp3_speed=250
```

保存后重启并检查：

```bash
sudo reboot
vcgencmd measure_temp
vcgencmd get_throttled
cat /sys/class/thermal/cooling_device0/cur_state
```

这比“一直满转”安静，也比 70°C 才启动更适合持续推理。不同第三方风扇控制板可能使用自己的守护程序，本节只适用于设备树控制的风扇。

---

## Step 14：基准与验收

准备至少 24 条 16kHz、单声道、16-bit ASR WAV：中文、英文和中英混合各 8 条，并填写 `benchmarks/asr_manifest.jsonl`。再准备 10 条中文、10 条英文和 10 个视觉问题，填写 `benchmarks/multimodal_manifest.jsonl`。

```bash
.venv/bin/python benchmarks/benchmark_asr.py benchmarks/asr_manifest.jsonl
.venv/bin/python benchmarks/benchmark_ollama.py benchmarks/multimodal_manifest.jsonl
.venv/bin/python benchmarks/soak_test.py --rounds 30
.venv/bin/python benchmarks/summarize_results.py --audit audit/pi-audit-时间.txt
```

验收目标：

- 30 轮成功率至少 95%，无服务崩溃或 OOM。
- ASR RTF ≤1.0。
- 文本请求停止录音到开始播报中位数 ≤15 秒。
- 带图请求中位数 ≤30 秒。
- 峰值内存约 ≤6.5GB，无持续 swap 抖动。
- 满载温度 <80°C，当前降频标志正常。

云端只用于手工离线对照：

```bash
.venv/bin/python benchmarks/export_cloud_jsonl.py benchmarks/multimodal_manifest.jsonl
```

正式应用没有云 API 依赖。

---

## 常见问题

### 模型回答“我没有摄像头”

先确认口令包含明确视觉动作，或直接勾选“附带当前画面”。系统必须先拍照，再把 JPEG 随请求送入模型；不能只把“请拍照”作为纯文本交给模型。

### 网页显示 `409 busy`

上一轮还在录音、推理或播报。等待状态回到 `IDLE`。系统不会无限排队。

### 麦克风录不到声音

```bash
arecord -l
arecord -D plughw:卡号,设备号 -d 5 -f S16_LE -r 16000 -c 1 /tmp/mic.wav
```

确认成功后修改 `AUDIO_CAPTURE_DEVICE` 并重启服务。

### 摄像头命令不存在

Bookworm 起使用 `rpicam-still`。确认安装了 `rpicam-apps`，不要继续照搬旧的 `libcamera-still` 教程。

### Piper 有文字但没有声音

确认两个 voice 的 ONNX 和 JSON 都存在，并手工运行 `aplay`。只想先验证问答时，可设置 `TTS_ENABLED=false`。

### Ollama 超时或内存不足

```bash
free -h
swapon --show
ollama ps
sudo journalctl -u ollama -n 100 --no-pager
```

先回到 2B、保持 4K 上下文和单并发；不要用扩大 microSD swap 掩盖长期内存不足。

### 服务没有随 SSH 注销继续运行

```bash
sudo loginctl enable-linger "$USER"
systemctl --user enable --now pi-edge-assistant
```

---

## 更新、停止与卸载

```bash
# 更新
cd ~/pi-edge-assistant
git pull --ff-only
.venv/bin/pip install '.[pi]'
systemctl --user restart pi-edge-assistant

# 停止
systemctl --user stop pi-edge-assistant

# 卸载应用服务但保留模型和历史
systemctl --user disable --now pi-edge-assistant
rm ~/.config/systemd/user/pi-edge-assistant.service
systemctl --user daemon-reload
```

这里不提供自动删除模型、历史或旧备份的脚本，避免误删用户数据。

## 旧教程中最容易踩的坑

- `df -h` 不能验证 swap，使用 `swapon --show` 和 `free -h`。
- Ollama 不存在统一的“必须 16GB 内存”，需求取决于模型、量化、上下文和并发。
- 不使用 `latest`，固定 `qwen3.5:2b` / `qwen3.5:4b` 并记录模型摘要。
- `rpicam-*` 取代旧教程里的 `libcamera-*` 主命令。
- whisper.cpp 当前用 CMake，程序位于 `build/bin/whisper-cli`。
- 使用 Python venv，不用 `--break-system-packages` 污染系统 Python。
- 4B 能载入不等于值得常用，依据应是质量提升、延迟、内存、温度和稳定性。

## 硬件升级判定

- 温度 ≥80°C 或发生降频：先检查官方电源和主动散热。
- 剩余空间 <15GB 或模型载入明显受 microSD I/O 限制：优先 NVMe，不扩大 swap。
- 只有以后需要摄像头常开目标检测、分割或姿态估计时，再评估 AI HAT+；它不能默认加速 Ollama LLM。
- 若 4B 质量必要但延迟仍不可接受，使用局域网服务器或手动云端路线，不在 microSD 上强行运行更大的模型。

## 本地开发与测试

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/pytest -q
```

测试覆盖访问口令、SQLite、双语视觉口令、语言分段、状态机、媒体清理、摄像头降级、并发 `409` 和完整 API 流程。

## 参考资料

- [Raspberry Pi OS 文档](https://www.raspberrypi.com/documentation/computers/os.html)
- [Raspberry Pi 摄像头软件](https://www.raspberrypi.com/documentation/computers/camera_software.html)
- [Picamera2 手册](https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf)
- [Ollama Qwen 3.5 模型列表](https://ollama.com/library/qwen3.5/tags)
- [whisper.cpp](https://github.com/ggml-org/whisper.cpp)
- [Piper voice 文档](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/VOICES.md)
- [Raspberry Pi AI HAT 文档](https://www.raspberrypi.com/documentation/accessories/ai-hat-plus.html)
