# 修复 Rust 目标安装问题

## 问题
```
error[E0463]: can't find crate for `core`
  = note: the `xtensa-esp32s3-espidf` target may not be installed
```

## 原因
ESP-IDF 的 Rust 目标（如 `xtensa-esp32s3-espidf`）不能直接用 `rustup target add` 安装，需要通过 `espup` 安装特殊的工具链。

**你的情况**：`espup` 已安装，但工具链还没有安装（`$HOME/.export-esp.sh` 不存在）。

## 快速修复（推荐）

运行安装脚本：

```bash
cd /Users/kingstonw/FCS_ws/WatusiPanel-V2
./install_rust_toolchain.sh
```

或者手动安装：

## 解决方案

### 步骤 1：安装 espup（如果还没有）

```bash
# 安装 espup
cargo install espup

# 验证安装
espup --version
```

### 步骤 2：安装 ESP-IDF Rust 工具链

```bash
# 设置 ESP-IDF 路径（如果还没有设置）
export ESP_IDF_PATH=/Users/kingstonw/esp/v6.0/esp-idf

# 安装 ESP-IDF Rust 工具链（这会下载工具链，可能需要 10-20 分钟）
espup install

# 设置环境变量
source $HOME/.export-esp.sh

# 验证安装
echo $ESP_IDF_VERSION
rustc --version
```

### 步骤 3：验证 Rust 目标

```bash
# 设置环境
source $HOME/.export-esp.sh

# 检查 Rust 目标（应该能看到 esp 相关的目标）
rustup target list | grep esp

# 或者直接尝试构建
cd rust_tasks
cargo build --release --target xtensa-esp32s3-espidf
```

### 步骤 4：如果 espup install 失败

#### 选项 A：使用现有的 ESP-IDF 安装

```bash
# 设置 ESP-IDF 路径
export ESP_IDF_PATH=/Users/kingstonw/esp/v6.0/esp-idf

# 安装工具链（espup 会使用现有的 ESP-IDF）
espup install
source $HOME/.export-esp.sh
```

#### 选项 B：手动指定 ESP-IDF 版本

```bash
# 安装指定版本的 ESP-IDF 工具链
espup install --esp-idf-version 6.0
source $HOME/.export-esp.sh
```

### 步骤 5：验证环境变量

确保以下环境变量已设置：

```bash
source $HOME/.export-esp.sh

# 检查关键环境变量
echo "ESP_IDF_VERSION: $ESP_IDF_VERSION"
echo "RUSTC: $(which rustc)"
echo "CARGO: $(which cargo)"

# 检查 Rust 目标
rustup target list | grep esp32s3
```

## 完整安装流程

```bash
# 1. 安装 Rust（如果还没有）
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source $HOME/.cargo/env

# 2. 安装 espup
cargo install espup

# 3. 设置 ESP-IDF 路径（根据你的实际路径调整）
export ESP_IDF_PATH=/Users/kingstonw/esp/v6.0/esp-idf

# 4. 安装 ESP-IDF Rust 工具链
espup install

# 5. 设置环境变量（添加到 ~/.zshrc）
echo 'source $HOME/.export-esp.sh' >> ~/.zshrc
source $HOME/.export-esp.sh

# 6. 验证安装
echo $ESP_IDF_VERSION
rustc --version
rustup target list | grep esp

# 7. 测试构建
cd /Users/kingstonw/FCS_ws/WatusiPanel-V2/rust_tasks
cargo build --release --target xtensa-esp32s3-espidf
```

## 常见问题

### Q: espup install 失败怎么办？

**A**: 检查：
1. ESP-IDF 路径是否正确
2. 网络连接是否正常（需要下载工具链）
3. 磁盘空间是否足够（工具链约 1-2 GB）

### Q: 如何知道工具链是否安装成功？

**A**: 运行：
```bash
source $HOME/.export-esp.sh
rustup target list | grep esp32s3
# 应该看到: xtensa-esp32s3-espidf (installed)
```

### Q: 可以跳过 espup，直接用 rustup 吗？

**A**: 不可以。ESP-IDF 的 Rust 目标需要特殊的工具链（xtensa-esp32s3-elf），只能通过 `espup` 安装。

## 验证清单

- [ ] Rust 已安装（`rustc --version`）
- [ ] espup 已安装（`espup --version`）
- [ ] ESP-IDF Rust 工具链已安装（`espup install` 成功）
- [ ] 环境变量已设置（`source $HOME/.export-esp.sh`）
- [ ] Rust 目标可用（`rustup target list | grep esp32s3`）
- [ ] 可以构建 Rust 库（`cargo build --release --target xtensa-esp32s3-espidf`）

## 快速修复命令

```bash
# 一键安装和验证
cargo install espup && \
export ESP_IDF_PATH=/Users/kingstonw/esp/v6.0/esp-idf && \
espup install && \
source $HOME/.export-esp.sh && \
echo "ESP_IDF_VERSION: $ESP_IDF_VERSION" && \
rustup target list | grep esp
```

