# 快速修复 Rust 构建错误

## 当前错误

```
error[E0463]: can't find crate for `core`
```

## 根本原因

**`espup install` 还没有运行**，所以 `$HOME/.export-esp.sh` 文件不存在。

## 快速修复（3 步）

### 步骤 1：安装 ESP-IDF Rust 工具链

```bash
# 设置 ESP-IDF 路径（根据你的实际路径调整）
export ESP_IDF_PATH=/Users/kingstonw/esp/v6.0/esp-idf

# 安装工具链（需要 10-20 分钟）
espup install
```

### 步骤 2：设置环境变量

```bash
# 临时设置（当前终端）
source $HOME/.export-esp.sh

# 永久设置（添加到 ~/.zshrc）
echo 'source $HOME/.export-esp.sh' >> ~/.zshrc
```

### 步骤 3：验证并重新构建

```bash
# 验证安装
echo $ESP_IDF_VERSION
rustup target list | grep esp32s3

# 重新构建
cd /Users/kingstonw/FCS_ws/WatusiPanel-V2
idf.py build
```

## 或者使用安装脚本

```bash
cd /Users/kingstonw/FCS_ws/WatusiPanel-V2
./install_rust_toolchain.sh
```

然后：

```bash
source $HOME/.export-esp.sh
idf.py build
```

## 验证清单

运行以下命令检查：

```bash
# 1. 检查 .export-esp.sh 是否存在
test -f $HOME/.export-esp.sh && echo "✅ 存在" || echo "❌ 不存在"

# 2. 检查环境变量
source $HOME/.export-esp.sh
echo "ESP_IDF_VERSION: $ESP_IDF_VERSION"

# 3. 检查 Rust 目标
rustup target list | grep esp32s3
# 应该看到: xtensa-esp32s3-espidf (installed)

# 4. 手动测试构建
cd rust_tasks
cargo build --release --target xtensa-esp32s3-espidf
```

## 常见问题

### Q: `espup install` 失败怎么办？

**A**: 检查：
1. ESP-IDF 路径是否正确：`echo $ESP_IDF_PATH`
2. 网络连接（需要下载工具链）
3. 磁盘空间（工具链约 1-2 GB）

### Q: 安装后仍然失败？

**A**: 确保：
1. 运行了 `source $HOME/.export-esp.sh`
2. 重新运行 `idf.py build`（不是 `idf.py reconfigure`）

### Q: 可以跳过 `espup` 吗？

**A**: 不可以。ESP-IDF 的 Rust 目标需要特殊的工具链，只能通过 `espup` 安装。

