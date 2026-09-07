# fishtank vendor/ —— 第三方运行时

本目录存放 **原样(verbatim)vendored 的第三方文件**,不是 openlimno 自己的代码,
任何情况下都不要手工编辑其内容。

| 文件 | 说明 |
|---|---|
| `three.module.min.js` | three.js **r165** 官方 minified ES module 构建(677,935 字节) |
| `THREE_LICENSE` | three.js 的 MIT 许可证原文(与上游 `LICENSE` 逐字节一致) |
| `PROVENANCE.json` | 机器可读的溯源记录:上游 URL、版本、SHA-256、获取时间、重新获取与校验命令 |

## 为什么要 vendor

fishtank Studio 的 3D 虚拟鱼缸需要 three.js 运行时。课程在**可能断网、或访问不到公共
CDN** 的学生机上讲授,不能在课堂上现拉 unpkg/jsdelivr,因此把运行时提交进仓库,由
`studio_http.py` 在本地以 `/assets/three.module.min.js` 路由发给浏览器。无构建步骤、
无 npm、无打包器。

## 溯源与校验

字段命名与 `openlimno.preprocess.fetch.sidecar`(即 `.openlimno_external_sources.json`
外部数据 sidecar)保持一致 —— 全项目一套溯源词汇,外部数据与 vendored 代码同一标准。

离线校验(不需要网络):

```bash
sha256sum src/openlimno/fishtank/vendor/three.module.min.js
# 期望 1af5bef9a9fd79fcb73fcfd3e4dd2ac0cea8720205bc7607d67369ce194a87fa
pytest tests/unit/test_vendor_provenance.py -q
```

`tests/unit/test_vendor_provenance.py` 会把上表里的 SHA-256 钉死:任何人替换或篡改
这个 blob,CI 都会变红。

重新从上游获取并逐字节比对(需要网络):

```bash
curl -sSL -o /tmp/three.module.min.js \
  https://raw.githubusercontent.com/mrdoob/three.js/r165/build/three.module.min.js
cmp /tmp/three.module.min.js src/openlimno/fishtank/vendor/three.module.min.js
```

## 升级 three.js 的流程

1. 从上游 tag 下载新的 `build/three.module.min.js` 与 `LICENSE`;
2. 同步更新 `PROVENANCE.json`(`release_tag` / `npm_version` / `produced_sha256` /
   `size_bytes` / `fetch_time` / `verification.last_verified`);
3. 重跑 `pytest tests/unit/test_vendor_provenance.py -q`(哈希对不上就是没更新记录);
4. 打开 Studio 冒烟一次 3D 缸,确认渲染没坏。
