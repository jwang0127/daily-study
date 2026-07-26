# Daily Study · 每日认识一个主题

一个每天用 1–2 小时认识一个新领域的静态知识导览。它不是课程，也不要求作业或深入实践；每天只提供背景、历史、主要参与者、争议和文章/视频/播客入口，并自动生成语音朗读版本。

## 快速开始

```bash
python scripts/generate_study.py
```

然后运行一个本地静态服务器并打开 `http://localhost:8000`：

```bash
python -m http.server 8000 --directory docs
```

脚本会先抓取主题资料页，再让 DeepSeek 根据真实网页内容写作。DeepSeek API 是每日文章的必要条件；如果没有 API Key、网页资料不足或模型返回无效内容，任务会失败并保留上一版页面，不再发布固定模板水文。

本地生成语音需要安装腾讯云 TTS SDK（没有密钥时会自动跳过音频，不影响文章）：

```bash
python -m pip install -r requirements.txt
```

## 接入 DeepSeek

在 GitHub 仓库中打开 `Settings → Secrets and variables → Actions → New repository secret`，新增：

```text
Name: DEEPSEEK_API_KEY
Value: 你的 DeepSeek API Key
```

不要把 Key 写进代码、JSON 或提交记录。GitHub Actions 发现这个 Secret 后，会每天抓取主题资料并调用一次 `deepseek-v4-flash` 生成文章。文章结构由当天资料决定，不强制套用固定栏目；调用失败会自动重试最多 3 次，仍失败则任务失败并保留上一版页面，避免用模板内容冒充新文章。

本地测试时可以在 PowerShell 临时设置：

```powershell
$env:DEEPSEEK_API_KEY = "你的 API Key"
python scripts\generate_study.py
```

测试完成后关闭当前 PowerShell 窗口即可清除临时变量。API 按输入和输出 token 计费，价格会变化，请以 DeepSeek 官方价格页为准。

## 自定义内容

编辑 `config/topics.json`：每个主题包含概览、历史、关键线索、热点关键词和文章/视频/播客入口。脚本会尽力读取百度热搜、知乎热榜和微博热搜；若网络或反爬导致失败，就从主题库随机选择。最近 7 天尽量不重复主题。给主题加 `publish_date`（如 `"2026-07-26"`）可以在指定日期强制发布。

## 页面与归档

- `index.html`：今日文章。加 `?date=YYYY-MM-DD` 参数可以查看任意一天的归档（`history.html` 中的条目就链接到这里），并支持前一天/后一天翻页。
- `history.html`：历史主题列表。
- `feed.xml`：Atom 订阅源，每天自动更新，可以加进任意 RSS 阅读器。
- `docs/audio/`：每日语音朗读（腾讯云 TTS）。为控制仓库体积，MP3 只保留最近 14 天（可用环境变量 `AUDIO_KEEP_DAYS` 调整）；过期后归档页会自动隐藏播放器，文字不受影响。

## GitHub Pages + 每日自动更新

1. 在仓库 Settings → Pages 中将 Source 设为 GitHub Actions。
2. 推送本仓库内容。
3. `.github/workflows/daily-study.yml` 会每天 09:00（北京时间）生成并提交新页面，也可以在 Actions 中手动 Run workflow。
4. 页面地址通常是 `https://jwang0127.github.io/daily-study/`（自定义部署可用环境变量 `SITE_BASE_URL` 覆盖订阅源里的站点地址）。

## 测试

纯逻辑部分（TTS 分段、MP3 合并、选题、编码探测、订阅源等）有离线单元测试，`.github/workflows/ci.yml` 会在提交与 PR 时自动运行：

```bash
python -m unittest discover -s tests -v
```

## 重要说明

这是学习与研究资料整理器，不构成投资、医疗或政治判断建议。热点只是选题线索，不等于事实结论；新闻、研究结论、观点和推测需要分别看待。链接可能随平台变化，页面保留了搜索入口作为备用。
