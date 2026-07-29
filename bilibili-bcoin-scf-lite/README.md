# Bilibili B-coin GitHub Actions

这是一个只保留主要功能的 Python 脚本：

- 领取年度大会员每月 B 币券和会员权益。
- 使用 B 币券给 UID `98399918` 充电。
- 充电成功后发送留言“支持”。

脚本只使用 Python 标准库，不需要安装第三方依赖。

## GitHub 配置

1. 将整个项目推送到 GitHub。
2. 打开仓库的 `Settings -> Secrets and variables -> Actions`。
3. 新增 Repository secret：

```text
BILI_COOKIE=完整的 B 站 Cookie
```

工作流文件是 `.github/workflows/bilibili-bcoin.yml`，会在每月 1 号 10:20（Asia/Shanghai）运行，也支持在 `Actions` 页面手动运行。

GitHub Actions 的定时任务只会从默认分支运行，且高负载时可能延迟。详见 [GitHub Actions schedule 文档](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)。

Cookie 等同于登录凭证，只放在 GitHub Secrets，不要写进代码、README 或日志。如果 Cookie 失效，重新获取后更新 `BILI_COOKIE` 即可。
