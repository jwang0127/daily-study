# Daily Study · 每日一题

一个每天用 1–2 小时掌握一个新主题的静态学习看板。页面由 Python 脚本生成，GitHub Actions 每天自动更新，也可以在本地运行。

## 快速开始

```bash
python scripts/generate_study.py
```

然后用浏览器打开 `docs/index.html`。脚本不需要第三方依赖，也不需要 API Key。

## 自定义内容

编辑 `config/topics.json`：每个主题包含学习目标、关键概念、练习问题、文章、视频和播客搜索入口。主题会按日期轮换；同一天重复运行会得到相同内容，方便复盘。

## GitHub Pages + 每日自动更新

1. 在仓库 Settings → Pages 中将 Source 设为 GitHub Actions。
2. 推送本仓库内容。
3. `.github/workflows/daily-study.yml` 会每天 07:00（北京时间）生成并提交新页面，也可以在 Actions 中手动 Run workflow。

## 重要说明

这是学习与研究资料整理器，不构成投资、医疗或政治判断建议。实时主题来自预先审核的课程库；链接可能随平台变化，页面保留了搜索入口作为备用。
