# Daily Study · 每日认识一个主题

一个每天用 1–2 小时认识一个新领域的静态知识导览。它不是课程，也不要求作业或深入实践；每天只提供背景、历史、主要参与者、争议和文章/视频/播客入口。

## 快速开始

```bash
python scripts/generate_study.py
```

然后运行一个本地静态服务器并打开 `http://localhost:8000`：

```bash
python -m http.server 8000 --directory docs
```

脚本不需要第三方依赖，也不需要 API Key。没有 API Key 时会使用本地备用文章；配置 DeepSeek 后会生成更长的 5000–8000 字中文导览。

## 可选：接入 DeepSeek

在 GitHub 仓库中打开 `Settings → Secrets and variables → Actions → New repository secret`，新增：

```text
Name: DEEPSEEK_API_KEY
Value: 你的 DeepSeek API Key
```

不要把 Key 写进代码、JSON 或提交记录。GitHub Actions 发现这个 Secret 后，会每天调用一次 `deepseek-v4-flash` 生成长文；调用失败时自动回退到本地主题库，不会让页面停止更新。

本地测试时可以在 PowerShell 临时设置：

```powershell
$env:DEEPSEEK_API_KEY = "你的 API Key"
python scripts\generate_study.py
```

测试完成后关闭当前 PowerShell 窗口即可清除临时变量。API 按输入和输出 token 计费，价格会变化，请以 DeepSeek 官方价格页为准。

## 自定义内容

编辑 `config/topics.json`：每个主题包含概览、历史、关键线索、热点关键词和文章/视频/播客入口。脚本会尽力读取百度热搜、知乎热榜和微博热搜；若网络或反爬导致失败，就从主题库随机选择。最近 7 天尽量不重复主题。

## GitHub Pages + 每日自动更新

1. 在仓库 Settings → Pages 中将 Source 设为 GitHub Actions。
2. 推送本仓库内容。
3. `.github/workflows/daily-study.yml` 会每天 09:00（北京时间）生成并提交新页面，也可以在 Actions 中手动 Run workflow。
4. 页面地址通常是 `https://jwang0127.github.io/daily-study/`。

## 重要说明

这是学习与研究资料整理器，不构成投资、医疗或政治判断建议。热点只是选题线索，不等于事实结论；新闻、研究结论、观点和推测需要分别看待。链接可能随平台变化，页面保留了搜索入口作为备用。
